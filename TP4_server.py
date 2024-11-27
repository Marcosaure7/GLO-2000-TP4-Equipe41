import hashlib
import hmac
import json
import os
import select
import socket
import sys
import re

import glosocket
import gloutils


class Server:
    """Serveur mail @glo2000.ca."""

    def __init__(self) -> None:
        """
        Prépare le socket du serveur `_server_socket`
        et le met en mode écoute.

        Prépare les attributs suivants:
        - `_client_socs` une liste des sockets clients.
        - `_logged_users` un dictionnaire associant chaque
            socket client à un nom d'utilisateur.

        S'assure que les dossiers de données du serveur existent.
        """
        self._server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_socket.bind(('0.0.0.0', gloutils.APP_PORT))
        self._server_socket.listen()
        self._client_socs: list[socket.socket] = []
        self._logged_users: dict[socket.socket, str]  = {}

    def cleanup(self) -> None:
        """Ferme toutes les connexions résiduelles."""
        for client_soc in self._client_socs:
            client_soc.close()
        self._server_socket.close()

    def _accept_client(self) -> None:
        """Accepte un nouveau client."""
        client_socket, _ = self._server_socket.accept()
        self._client_socs.append(client_socket)

    def _remove_client(self, client_soc: socket.socket) -> None:
        """Retire le client des structures de données et ferme sa connexion."""
        if client_soc in self._client_socs:
            self._client_socs.remove(client_soc)
        client_soc.close()
        if client_soc in self._logged_users:
            del self._logged_users[client_soc]

    def _create_account(self, client_soc: socket.socket,
                        payload: gloutils.AuthPayload
                        ) -> gloutils.GloMessage:
        """
        Crée un compte à partir des données du payload.

        Si les identifiants sont valides, créee le dossier de l'utilisateur,
        associe le socket au nouvel utilisateur et retourne un succès,
        sinon retourne un message d'erreur.
        """
        _username = payload["username"]
        _password = payload["password"]

        # Vérification des caractères interdits
        if re.search(r"[_.-]", _username) is not None:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le username contient des caractères interdits."}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

        # Vérification username inexistant
        list_usernames_lowered = [username.lower() for username in os.listdir(gloutils.SERVER_DATA_DIR) if os.path.isdir(os.path.join(gloutils.SERVER_DATA_DIR, username))]
        if _username.lower() in list_usernames_lowered:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le username est déjà utilisé."}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

        # Vérification force du password
        if len(_password) < 10 or re.search(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d]+$", _password) is None:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le mot de passe n'est pas assez fort."}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

        # À partir d'ici on sait que l'utilisateur et son mot de passe sont OK
        # donc on l'ajoute à SERVER_DATA_DIR
        path = f"{gloutils.SERVER_DATA_DIR}/{_username}"
        os.makedirs(path, exist_ok=True)
        hashed_pass = hashlib.sha3_512(_password.encode()).hexdigest()

        with open(os.path.join(path, gloutils.PASSWORD_FILENAME), 'w') as file_pass:
            file_pass.write(hashed_pass)

        self._logged_users[client_soc] = _username

        return gloutils.GloMessage(header=gloutils.Headers.OK)

    def _login(self, client_soc: socket.socket, payload: gloutils.AuthPayload
               ) -> gloutils.GloMessage:
        """
        Vérifie que les données fournies correspondent à un compte existant.

        Si les identifiants sont valides, associe le socket à l'utilisateur et
        retourne un succès, sinon retourne un message d'erreur.
        """
        username = payload["username"]
        password = payload["password"]

        # On vérifie si l'utilisateur existe dans la base de données
        if username not in os.listdir(gloutils.SERVER_DATA_DIR):
            error_payload = gloutils.ErrorPayload(error_message="Le nom d'utilisateur n'est pas dans la base de données.")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

        # On hache le mot de passe pour le comparer à celui enregistré
        hashed_pass = hashlib.sha3_512(password.encode()).hexdigest()
        with open(f"{gloutils.SERVER_DATA_DIR}/{username}/{gloutils.PASSWORD_FILENAME}", 'r') as pass_file:
            stored_pass = pass_file.read().strip()

        # On compare le mot de passe entré à celui enregistré
        if hashed_pass != stored_pass:
            error_payload = gloutils.ErrorPayload(error_message="Le mot de passe dans la base de données ne correspond pas à celui entré.")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

        # Tout est bon, on connecte le socket client à son username
        self._logged_users[client_soc] = username
        return gloutils.GloMessage(header=gloutils.Headers.OK)

    def _send_email(self, client_soc: socket.socket, payload: gloutils.EmailContentPayload
                    ) -> gloutils.GloMessage:
        """
        Détermine si l'envoi est interne ou externe et:
        - Si l'envoi est interne, écris le message tel quel dans le dossier
        du destinataire.
        - Si le destinataire n'existe pas, place le message dans le dossier
        SERVER_LOST_DIR et considère l'envoi comme un échec.
        - Si le destinataire est externe, considère l'envoi comme un échec.

        Retourne un message indiquant le succès ou l'échec de l'opération.
        """
        recipient = payload["destination"]
        if recipient.endswith("@glo2000.ca"):
            recipient_name = recipient.split("@")[0]
            recipient_path = os.path.join(gloutils.SERVER_DATA_DIR, recipient_name)

            if recipient_name in os.listdir(gloutils.SERVER_DATA_DIR):
                email_path = os.path.join(recipient_path, f"email_{len(os.listdir(recipient_path)) + 1}.json")
                with open(email_path, 'w', encoding='utf-8') as email_file:
                    json.dump(payload, email_file)
                return gloutils.GloMessage(header=gloutils.Headers.OK)
            else:
                lost_path = os.path.join(gloutils.SERVER_LOST_DIR, f"lost_email_{len(os.listdir(gloutils.SERVER_LOST_DIR)) + 1}.json")
                with open(lost_path, 'w', encoding='utf-8') as lost_file:
                    json.dump(payload, lost_file)
                error_payload = gloutils.ErrorPayload(error_message="Le destinataire n'existe pas. Le message a été placé dans le dossier perdu.")
                return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)
        else:
            # Envoi externe
            error_payload = gloutils.ErrorPayload(error_message="Le destinataire est externe. L'envoi a échoué.")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

    def handle_client(self, client_soc: socket.socket) -> None:
        message = glosocket.recv_mesg(client_soc)
        rep: gloutils.GloMessage = eval(message)
        if rep.get("header") == gloutils.Headers.AUTH_LOGIN:
            self.send_conection_confirmation(rep, client_soc)
        elif rep["header"] == gloutils.Headers.AUTH_REGISTER:
            self._create_account(client_soc, rep["payload"])
        elif rep["header"] == gloutils.Headers.AUTH_LOGIN:
            self._login(client_soc, rep["payload"])
        elif rep["header"] == gloutils.Headers.EMAIL_SENDING:
            response = self._send_email(client_soc, rep["payload"])
            glosocket.snd_mesg(client_soc, str(response))

    def run(self):
        """Point d'entrée du serveur."""
        while True:
            # Select readable sockets
            result = select.select(
                [self._server_socket] + self._client_socs,  # Vérifie la lecture est possible
                [],  # Vérifie si l'écriture est possible (ne pas utiliser)
                []   # Vérifie les conditions exceptionnelles (ne pas utiliser)
            )
            waiters: list[socket.socket] = result[0]
            for waiter in waiters:
                # Handle sockets
                if waiter == self._server_socket:
                    self._accept_client()
                else:
                    self.handle_client(waiter)

def _main() -> int:
    server = Server()
    try:
        server.run()
    except KeyboardInterrupt:
        print("Arrêt du serveur...")
    finally:
        server.cleanup()
    return 0

if __name__ == '__main__':
    sys.exit(_main())
