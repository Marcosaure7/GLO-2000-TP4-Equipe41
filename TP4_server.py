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

        if not os.path.exists(gloutils.SERVER_DATA_DIR): os.mkdir(gloutils.SERVER_DATA_DIR)

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
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

        # Vérification username inexistant
        list_usernames_lowered = [username.lower() for username in os.listdir(gloutils.SERVER_DATA_DIR)]
        if _username.lower() in list_usernames_lowered:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le username est déjà utilisé."}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)


        # Vérification force du password
        if len(_password) < 10 or re.search(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d]+$", _password) is None:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le mot de passe n'est pas assez fort."}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

        # À partir d'ici on sait que l'utilisateur et son mot de passe sont OK
        # donc on l'ajoute à SERVER_DATA_DIR
        path = f"{gloutils.SERVER_DATA_DIR}/{_username}"
        os.makedirs(path, exist_ok=True)
        hashed_pass = hashlib.sha3_512(_password.encode()).hexdigest()

        with open(os.path.join(path, gloutils.PASSWORD_FILENAME), 'w') as file_pass:
            file_pass.write(hashed_pass)

        self._logged_users[client_soc] = _username

        return gloutils.GloMessage(header=gloutils.Headers.OK.value)

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
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

        # On hache le mot de passe pour le comparer à celui enregistré
        hashed_pass = hashlib.sha3_512(password.encode()).hexdigest()
        with open(f"{gloutils.SERVER_DATA_DIR}/{username}/{gloutils.PASSWORD_FILENAME}", 'r') as pass_file:
            stored_pass = pass_file.read().strip()

        # On compare le mot de passe entré à celui enregistré
        if hashed_pass != stored_pass:
            error_payload = gloutils.ErrorPayload(error_message="Le mot de passe dans la base de données ne correspond pas à celui entré.")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

        # Tout est bon, on connecte le socket client à son username
        self._logged_users[client_soc] = username
        return gloutils.GloMessage(header=gloutils.Headers.OK.value)

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
                return gloutils.GloMessage(header=gloutils.Headers.OK.value)
            else:
                lost_path = os.path.join(gloutils.SERVER_LOST_DIR, f"lost_email_{len(os.listdir(gloutils.SERVER_LOST_DIR)) + 1}.json")
                with open(lost_path, 'w', encoding='utf-8') as lost_file:
                    json.dump(payload, lost_file)
                error_payload = gloutils.ErrorPayload(error_message="Le destinataire n'existe pas. Le message a été placé dans le dossier perdu.")
                return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)
        else:
            # Envoi externe
            error_payload = gloutils.ErrorPayload(error_message="Le destinataire est externe. L'envoi a échoué.")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

    def _get_email_list(self, client_soc: socket.socket) -> gloutils.GloMessage:
        """
        Récupère et renvoie la liste des courriels pour l'utilisateur connecté.
        Met à jour le cache centralisé avec la liste.
        """
        try:
            # Vérification de l'utilisateur connecté
            username = self._logged_users.get(client_soc)
            if not username:
                error_payload = gloutils.ErrorPayload(error_message="Utilisateur non authentifié.")
                return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

            # Chemin du dossier utilisateur
            user_dir = os.path.join(gloutils.SERVER_DATA_DIR, username)

            # Vérification du dossier utilisateur
            if not os.path.exists(user_dir):
                self._email_cache[username] = []  # Mettre à jour le cache avec une liste vide
                return gloutils.GloMessage(header=gloutils.Headers.OK.value, payload={"email_list": []})

            # Récupération et tri des fichiers d'emails par date
            email_files = sorted(
                [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))],
                key=lambda f: os.path.getmtime(os.path.join(user_dir, f)),
                reverse=True
            )

            # Construction de la liste des courriels en respectant le formatqge demander
            email_list = []
            for index, filename in enumerate(email_files, start=1):
                email_path = os.path.join(user_dir, filename)
                try:
                    with open(email_path, "r", encoding="utf-8") as email_file:
                        email_data = json.load(email_file)
                        formatted_email = gloutils.SUBJECT_DISPLAY.format(
                            number=index,
                            sender=email_data.get("sender", "Inconnu"),
                            subject=email_data.get("subject", "Sans sujet"),
                            date=email_data.get("date", "Date inconnue")
                        )
                        email_list.append({"formatted": formatted_email, "filename": filename})
                except json.JSONDecodeError:
                    continue

            # Mettre à jour le cache utilisateur pour pouvoir l'utuliser dans get email
            self._email_cache[username] = email_list

            # Retourner la liste formatée
            return gloutils.GloMessage(
                header=gloutils.Headers.OK.value,
                payload={"email_list": [email["formatted"] for email in email_list]}
            )

        except OSError as ex:
            error_payload = gloutils.ErrorPayload(
                error_message=f"Erreur lors de la récupération des courriels : {str(ex)}")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)



    def _get_stats(self, client_soc: socket.socket) -> gloutils.GloMessage:
        """
        Récupère les statistiques sur les courriels d'un utilisateur.
        Retourne un GloMessage structuré avec le nombre de courriels et la taille totale du dossier.
        """
        try:
            # Vérification de l'utilisateur connecté
            username = self._logged_users.get(client_soc)
            if not username:
                error_payload = gloutils.ErrorPayload(error_message="Utilisateur non authentifié.")
                return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

            # Récupération du dossier utilisateur et initiatiliser le cout et le size a 0
            user_dir = os.path.join(gloutils.SERVER_DATA_DIR, username)
            if not os.path.exists(user_dir):
                return gloutils.GloMessage(
                    header=gloutils.Headers.OK.value,
                    payload={"count": 0, "size": 0}
                )

            # Calcul des statistiques
            email_files = [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))]
            count = len(email_files)
            size = sum(os.path.getsize(os.path.join(user_dir, f)) for f in email_files)

            # Retour des statistiques
            return gloutils.GloMessage(
                header=gloutils.Headers.OK.value,
                payload={"count": count, "size": size}
            )

        except OSError:
            error_payload = gloutils.ErrorPayload(
                error_message=f"Erreur lors de la récupération des statistiques : {str(ex)}")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

    def _get_email(self, client_soc: socket.socket, payload: gloutils.EmailChoicePayload) -> gloutils.GloMessage:
        """
        Récupère le contenu d'un courriel spécifique en réutilisant le cache centralisé.
        """
        try:
            # Vérification de l'utilisateur connecté
            username = self._logged_users.get(client_soc)
            if not username:
                error_payload = gloutils.ErrorPayload(error_message="Utilisateur non authentifié.")
                return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

            # Vérification du cache utilisateur
            if username not in self._email_cache or not self._email_cache[username]:
                error_payload = gloutils.ErrorPayload(error_message="La liste des courriels est vide ou non chargée.")
                return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

            # Récupération du choix utilisateur
            choice = payload.get("choice", 0)
            # choise = payload["choice"]
            email_list = self._email_cache[username]
            if choice < 1 or choice > len(email_list):
                error_payload = gloutils.ErrorPayload(error_message="Choix de courriel invalide.")
                return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)

            # Lecture du fichier correspondant au choix de l'utulisatuer
            selected_email = email_list[choice - 1]
            email_path = os.path.join(gloutils.SERVER_DATA_DIR, username, selected_email["filename"])
            with open(email_path, "r", encoding="utf-8") as email_file:
                email_data = json.load(email_file)

            # Structurer le payload pour le courriel

            email_payload : gloutils.EmailContentPayload = email_data

            return gloutils.GloMessage(header=gloutils.Headers.OK.value, payload=email_payload)

        except Exception as ex:
            error_payload = gloutils.ErrorPayload(
                error_message=f"Erreur lors de la récupération du courriel : {str(ex)}")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR.value, payload=error_payload)



    def handle_client(self, client_soc: socket.socket) -> None:
        message = glosocket.recv_mesg(client_soc)
        rep: gloutils.GloMessage = eval(message)
        if rep["header"] == gloutils.Headers.AUTH_REGISTER:
            message = self._create_account(client_soc, rep["payload"])
        elif rep["header"] == gloutils.Headers.AUTH_LOGIN:
            message = self._login(client_soc, rep["payload"])
        elif rep["header"] == gloutils.Headers.EMAIL_SENDING:
            message = self._send_email(client_soc, rep["payload"])
        elif rep["header"] == gloutils.Headers.INBOX_READING_REQUEST:
            message = self._get_email_list(client_soc)
        elif rep["header"] == gloutils.Headers.INBOX_READING_CHOICE:
            message = self._get_email(client_soc, rep["payload"])
        elif rep["header"] == gloutils.Headers.STATS_REQUEST:
            message = self._get_stats(client_soc)

        glosocket.snd_mesg(client_soc, str(message))

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
