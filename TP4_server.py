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
        return gloutils.GloMessage()

    def _login(self, client_soc: socket.socket, payload: gloutils.AuthPayload
               ) -> gloutils.GloMessage:
        """
        Vérifie que les données fournies correspondent à un compte existant.

        Si les identifiants sont valides, associe le socket à l'utilisateur et
        retourne un succès, sinon retourne un message d'erreur.
        """
        username = payload.get("username")
        password = payload.get("password")
        mess = gloutils.GloMessage()
        mess["header"] = gloutils.Headers.OK
        return mess


    def _logout(self, client_soc: socket.socket) -> None:
        """Déconnecte un utilisateur."""

    def _get_email_list(self, client_soc: socket.socket
                        ) -> gloutils.GloMessage:
        """
        Récupère la liste des courriels de l'utilisateur associé au socket.
        Les éléments de la liste sont construits à l'aide du gabarit
        SUBJECT_DISPLAY et sont ordonnés du plus récent au plus ancien.

        Une absence de courriel n'est pas une erreur, mais une liste vide.
        """
        return gloutils.GloMessage()

    def _get_email(self, client_soc: socket.socket,
                   payload: gloutils.EmailChoicePayload
                   ) -> gloutils.GloMessage:
        """
        Récupère le contenu de l'email dans le dossier de l'utilisateur associé
        au socket.
        """
        return gloutils.GloMessage()

    def _get_stats(self, client_soc: socket.socket) -> gloutils.GloMessage:
        """
        Récupère le nombre de courriels et la taille du dossier et des fichiers
        de l'utilisateur associé au socket.
        """
        return gloutils.GloMessage()

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
        elif ():
            pass


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
