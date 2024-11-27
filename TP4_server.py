"""\
GLO-2000 Travail pratique 4 - Serveur
Noms et numéros étudiants:
-
-
-
"""

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
        self._server_socket = socket.socket(socket.AF_INET, gloutils.APP_PORT)
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

    def _remove_client(self, client_soc: socket.socket) -> None:
        """Retire le client des structures de données et ferme sa connexion."""

    def _create_account(self, client_soc: socket.socket,
                        payload: gloutils.AuthPayload
                        ) -> gloutils.GloMessage:
        """
        Crée un compte à partir des données du payload.

        Si les identifiants sont valides, créee le dossier de l'utilisateur,
        associe le socket au nouvel l'utilisateur et retourne un succès,
        sinon retourne un message d'erreur.
        """
        _username = payload["username"]
        # username_ok = False

        _password = payload["password"]
        # password_ok = False
        
        # Vérification des caractères interdits
        if re.search(r"[_.-]", _username) is not None:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le username contient des caractères interdits."}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)
        
        # Vérification username inexistant
        list_usernames_lowered = [username.lower() for username in os.listdir if os.path.isdir(username)]
        if _username.lower() in list_usernames_lowered:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le username est déjà utilisé."}
            message_derreur: gloutils.GloMessage = {"header": gloutils.Headers.ERROR, "payload":error_payload}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)
        

        # Vérification force du password
        if len(_password) < 10 and re.search(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)[a-zA-Z\d]+$", _password) is None:
            error_payload: gloutils.ErrorPayload = {"error_message": "Le mot de passe n'est pas assez fort."}
            message_derreur: gloutils.GloMessage = {"header": gloutils.Headers.ERROR, "payload":error_payload}
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

        # À partir d'ici on sait que l'utilisateur et son mot de passe sont OK
        # donc on l'ajoute à SERVER_DATA_DIR

        path = f"{gloutils.SERVER_DATA_DIR}/{_username}"
        os.makedirs(path, exist_ok=True)
        hashed_pass = hashlib.sha3_512(_password)

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
        hashed_pass = hashlib.sha3_512(password)
        pass_file = open(f"{gloutils.SERVER_DATA_DIR}/{username}/{gloutils.PASSWORD_FILENAME}")

        # On compare le mot de passe entré à celui enregistré
        if hashed_pass is not pass_file.read():
            error_payload = gloutils.ErrorPayload(error_message="Le mot de passe dans la base de données ne correspond pas à celui entré.")
            return gloutils.GloMessage(header=gloutils.Headers.ERROR, payload=error_payload)

        # Tout est bon, on connecte le socket client à son username
        self._logged_users[client_soc] = username
        return gloutils.GloMessage(header=gloutils.Headers.OK)

    def _logout(self, client_soc: socket.socket) -> None:
        """Déconnecte un utilisateur."""

    def _get_email_list(self, client_soc: socket.socket
                        ) -> gloutils.GloMessage:
        """
        Récupère la liste des courriels de l'utilisateur associé au socket.
        Les éléments de la liste sont construits à l'aide du gabarit
        SUBJECT_DISPLAY et sont ordonnés du plus récent au plus ancien.
        Une absence de courriels n'est pas une erreur, mais retourne une liste vide.
        """
        try:
            # Vérification de l'utilisateur connecté
            username = self._logged_users.get(client_soc)
            if not username:
                return {
                    "header": gloutils.Headers.ERROR,
                    "payload": {"error_message": "Utilisateur non authentifié."}
                }

            # Récupération des fichiers d'emails triés
            user_dir = os.path.join(gloutils.SERVER_DATA_DIR, username)
            if not os.path.exists(user_dir):
                return {"header": gloutils.Headers.OK, "payload": {"email_list": []}}

            email_files = sorted(
                [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))],
                key=lambda f: os.path.getmtime(os.path.join(user_dir, f)),
                reverse=True
            )

            # Construction de la liste formatée
            email_list = []
            for index, filename in enumerate(email_files, start=1):
                email_path = os.path.join(user_dir, filename)
                with open(email_path, "r", encoding="utf-8") as email_file:
                    try:
                        email_data = json.load(email_file)
                        formatted_email = gloutils.SUBJECT_DISPLAY.format(
                            number=index,
                            sender=email_data.get("sender", "Inconnu"),
                            subject=email_data.get("subject", "Sans sujet"),
                            date=email_data.get("date", "Date inconnue")
                        )
                        email_list.append(formatted_email)
                    except json.JSONDecodeError:
                        continue

            return {"header": gloutils.Headers.OK, "payload": {"email_list": email_list}}

        except Exception as ex:
            return {"header": gloutils.Headers.ERROR, "payload": {"error_message": str(ex)}}

    def _get_email(self, client_soc: socket.socket,
                   payload: gloutils.EmailChoicePayload
                   ) -> gloutils.GloMessage:
        """
        Récupère le contenu de l'email sélectionné dans le dossier de l'utilisateur
        associé au socket.
        """
        try:
            # Appeler _get_email_list pour récupérer la liste des courriels
            email_list_response = self._get_email_list(client_soc)

            # Vérifier si _get_email_list a retourné une erreur
            if email_list_response["header"] == gloutils.Headers.ERROR:
                return email_list_response

            # Récupérer les fichiers associés à l'utilisateur
            username = self._logged_users.get(client_soc)
            user_dir = os.path.join(gloutils.SERVER_DATA_DIR, username)
            email_files = sorted(
                [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))],
                key=lambda f: os.path.getmtime(os.path.join(user_dir, f)),
                reverse=True
            )

            # Validation du choix de l'utilisateur
            choice = payload.get("choice", 0)
            if choice < 1 or choice > len(email_files):
                return {
                    "header": gloutils.Headers.ERROR,
                    "payload": {"error_message": "Choix de courriel invalide."}
                }

            # Lecture du fichier correspondant
            email_path = os.path.join(user_dir, email_files[choice - 1])
            with open(email_path, "r", encoding="utf-8") as email_file:
                email_data = json.load(email_file)

            # Créer un EmailContentPayload
            email_payload: gloutils.EmailContentPayload = {
                "sender": email_data.get("sender", "Inconnu"),
                "destination": email_data.get("destination", "Inconnu"),  # Utilisez "destination"
                "subject": email_data.get("subject", "Sans sujet"),
                "date": email_data.get("date", "Date inconnue"),
                "content": email_data.get("content", "")  # Utilisez "content"
            }

            # Retourner le message structuré
            return {
                "header": gloutils.Headers.OK,
                "payload": email_payload
            }

        except Exception as ex:
            return {
                "header": gloutils.Headers.ERROR,
                "payload": {"error_message": str(ex)}
            }

    def _get_stats(self, client_soc: socket.socket) -> gloutils.GloMessage:
        """
        Récupère le nombre de courriels et la taille du dossier et des fichiers
        de l'utilisateur associé au socket.
        """
        try:
            username = self._logged_users.get(client_soc)
            if not username:
                return {
                    "header": gloutils.Headers.ERROR,
                    "payload": {"error_message": "Utilisateur non authentifié."}
                }

            user_dir = os.path.join(gloutils.SERVER_DATA_DIR, username)
            if not os.path.exists(user_dir):
                return {
                    "header": gloutils.Headers.ERROR,
                    "payload": {"error_message": "Dossier utilisateur introuvable."}
                }

            email_files = [f for f in os.listdir(user_dir) if os.path.isfile(os.path.join(user_dir, f))]
            count = len(email_files)
            size = sum(os.path.getsize(os.path.join(user_dir, f)) for f in email_files)

            return {
                "header": gloutils.Headers.OK,
                "payload": {"count": count, "size": size}
            }
        except Exception as ex:
            return {
                "header": gloutils.Headers.ERROR,
                "payload": {"error_message": str(ex)}
            }

    def _send_email(self, payload: gloutils.EmailContentPayload
                    ) -> gloutils.GloMessage:
        """
        Détermine si l'envoi est interne ou externe et:
        - Si l'envoi est interne, écris le message tel quel dans le dossier
        du destinataire.
        - Si le destinataire n'existe pas, place le message dans le dossier
        SERVER_LOST_DIR et considère l'envoi comme un échec.
        - Si le destinataire est externe, considère l'envoi comme un échec.

        Retourne un messange indiquant le succès ou l'échec de l'opération.
        """
        return gloutils.GloMessage()

# class GloMessage(TypedDict, total=False):
#     """
#     Classe à utiliser pour générer des messages.

#     Les classes *Payload correspondent à des entêtes spécifiques
#     certaines entêtes n'ont pas besoin de payload.
#     """
#     header: Headers
#     payload: Union[ErrorPayload, AuthPayload, EmailContentPayload,
#                    EmailListPayload, EmailChoicePayload, StatsPayload]
#

    def send_conection_confirmation(self, rep : gloutils.GloMessage , client_soc: socket.socket) -> None:
        payload = rep.get("payload")
        if (type(payload) == gloutils.AuthPayload):
            rep = self._login(client_soc, payload)
            if (rep.get("header") == gloutils.Headers.OK):
                self._logged_users[client_soc] = payload.get("username")
                glosocket.snd_mesg(client_soc, str(rep))
            else:
                glosocket.snd_mesg(client_soc, str(rep))


    def handle_client(self, client_soc: socket.socket) -> None:
        message = glosocket.recv_mesg(client_soc)
        rep : gloutils.GloMessage = eval(message)
        if rep.get("header") == gloutils.Headers.AUTH_LOGIN:
            self.send_conection_confirmation(rep, client_soc)
        elif rep["header"] is gloutils.Headers.AUTH_REGISTER:
            self._create_account(client_soc, rep["payload"])
        elif rep["header"] is gloutils.Headers.AUTH_LOGIN:
            self._login(client_soc, rep["payload"])


    def run(self):
        """Point d'entrée du serveur."""
        waiters = []
        while True:
            # Select readable sockets
            result = select.select(
                [self._server_socket] + self._client_socs, # Vérifie la lecture est possible
                [], # Vérifie si l'écriture est possible (ne pas utiliser)
                []  # Vérifie les conditions exceptionnelles (ne pas utiliser)
            )
            waiters: list[socket.socket] = result[0]
            for waiter in waiters:
                # Handle sockets
                # Si le socket est celui du serveur, un nouveau client est en
                # train de se connecter
                if waiter == self._server_socket:
                    self._accept_client()
                # Sinon, on traite le client.
                else:
                    self.handle_client(waiter)



def _main() -> int:
    server = Server()
    try:
        server.run()
    except KeyboardInterrupt:
        server.cleanup()
    return 0


# def _main() -> NoReturn:
#     server_socket = _make_socket()

#     while True:
#         # On passe à select comme premier argument une liste contenant les
#         # sockets des clients et du serveur
#         result = select.select(
#             [server_socket] + _client_list, # Vérifie la lecture est possible
#             [], # Vérifie si l'écriture est possible (ne pas utiliser)
#             []  # Vérifie les conditions exceptionnelles (ne pas utiliser)
#         )
#         # Le résultat est un tuple de trois listes. La liste des sockets prêts
#         # à être lu est toujours le premier élément de ce tuple.
#         readable_socket: list[socket.socket] = result[0]

#         for soc in readable_socket:
#             # Si le socket est celui du serveur, un nouveau client est en
#             # train de se connecter
#             if soc == server_socket:
#                 _new_client(soc)
#             # Sinon, on traite le client.
#             else:
#                 _process_client(soc)

if __name__ == '__main__':
    sys.exit(_main())
