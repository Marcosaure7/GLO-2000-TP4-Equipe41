"""\
GLO-2000 Travail pratique 4 - Client
Noms et numéros étudiants:
-
-
-
"""

import argparse
import getpass
import json
import socket
import sys

import glosocket
import gloutils


class Client:
    """Client pour le serveur mail @glo2000.ca."""

    def __init__(self, destination: str) -> None:
        """
        Prépare et connecte le socket du client `_socket`.

        Prépare un attribut `_username` pour stocker le nom d'utilisateur
        courant. Laissé vide quand l'utilisateur n'est pas connecté.
        """
        
        try:
            self._socket = glosocket.socket.socket(glosocket.socket.AF_INET, glosocket.socket.SOCK_STREAM)
            address = (destination, gloutils.APP_PORT)
            self._socket.connect(address)
    
        except glosocket.GLOSocketError:
            print("Le client n'a pas pu se connecter.")
            sys.exit(1)


        self._username = ""

    def _register(self) -> None:
        """
        Demande un nom d'utilisateur et un mot de passe et les transmet au
        serveur avec l'entête `AUTH_REGISTER`.

        Si la création du compte s'est effectuée avec succès, l'attribut
        `_username` est mis à jour, sinon l'erreur est affichée.
        """
        
        username_temp = input(" Entrez un nom d'utilisateur: ")
        password_temp = getpass.getpass("Entrez un mot de passe : ")
        
        try:
            auth_payload: gloutils.AuthPayload = {"username": username_temp, "password": password_temp}
            message: gloutils.GloMessage = {"header": gloutils.Headers.AUTH_REGISTER.value, "payload": auth_payload}

            glosocket.snd_mesg(self._socket, str(message))
            reponse: gloutils.GloMessage = eval(glosocket.recv_mesg(self._socket))
            
            if reponse["header"] == gloutils.Headers.OK:
                self._username = username_temp
                self._password = password_temp
            
            elif reponse["header"] == gloutils.Headers.ERROR:
                print(reponse["payload"]["error_message"])
        

        except glosocket.GLOSocketError:
            print("Le client n'a pas réussi à envoyer les informations de compte au serveur.")


    def _login(self) -> None:
        """
        Demande un nom d'utilisateur et un mot de passe et les transmet au
        serveur avec l'entête `AUTH_LOGIN`.

        Si la connexion est effectuée avec succès, l'attribut `_username`
        est mis à jour, sinon l'erreur est affichée.
        """

        username_temp = input(" Entrez votre nom d'utilisateur: ")
        password_temp = getpass.getpass("Entrez votre mot de passe : ")

        try:
            auth_payload: gloutils.AuthPayload = {"username": username_temp, "password": password_temp}
            message: gloutils.GloMessage = {"header": gloutils.Headers.AUTH_LOGIN.value, "payload": auth_payload}

            glosocket.snd_mesg(self._socket, str(message))
            reponse: gloutils.GloMessage = eval(glosocket.recv_mesg(self._socket))
            
            if reponse["header"] == gloutils.Headers.OK:
                self._username = username_temp
                self._password = password_temp

            elif reponse["header"] == gloutils.Headers.ERROR:
                print(reponse["payload"]["error_message"])

        except glosocket.GLOSocketError:
            print("Le client n'a pas réussi à envoyer les informations de compte au serveur.")


    def _quit(self) -> None:
        """
        Préviens le serveur de la déconnexion avec l'entête `BYE` et ferme le
        socket du client.
        """

        try:
            message_bye: gloutils.GloMessage = {"header":gloutils.Headers.BYE.value}
            glosocket.snd_mesg(self._socket, str(message_bye))
            self._socket.close()
            
        except glosocket.GLOSocketError:
            print("Le client n'a pas réussi à envoyer la requête de fermeture au serveur")


    def _read_email(self) -> None:
        """
        Demande au serveur la liste de ses courriels avec l'entête
        `INBOX_READING_REQUEST`.

        Affiche la liste des courriels puis transmet le choix de l'utilisateur
        avec l'entête `INBOX_READING_CHOICE`.

        Affiche le courriel à l'aide du gabarit `EMAIL_DISPLAY`.

        S'il n'y a pas de courriel à lire, l'utilisateur est averti avant de
        retourner au menu principal.
        """

        try:
            message: gloutils.GloMessage = {"header": gloutils.Headers.INBOX_READING_REQUEST.value}

            glosocket.snd_mesg(self._socket, str(message))
            reponse: gloutils.GloMessage = eval(glosocket.recv_mesg(self._socket))
            
            if reponse["header"] != gloutils.EmailListPayload:
                print("Il y a eu erreur côté serveur.")
                return

            email_list = reponse["payload"]["email_list"]

            for email in email_list:
                print(email)

            num_courriel_a_consulter = self._user_choice_in_email_list(range(1, len(email_list)))
            
            email_choice_payload: gloutils.EmailChoicePayload = {"choice": num_courriel_a_consulter}
            message: gloutils.GloMessage = {"header": gloutils.Headers.INBOX_READING_CHOICE.value, "payload":email_choice_payload}

            glosocket.snd_mesg(self._socket, str(message))
            reponse: gloutils.GloMessage = eval(glosocket.recv_mesg(self._socket))

            formatted_email = f'{gloutils.SUBJECT_DISPLAY.format(**reponse["payload"])}\n{gloutils.EMAIL_DISPLAY.format(**reponse["payload"])}'
            print(formatted_email)
            

        except glosocket.GLOSocketError:
            print("Le client n'a pas réussi à envoyer la requête de courriel(s) au serveur.")


    def _user_choice_in_email_list(self, email_nb_list):
        """
        Demande à l'utilisateur un choix dans la liste de courriels présentée à lui.
        """
        while (True):
            try:
                num_courriel_a_consulter = input(f"Entrez votre choix [{email_nb_list[0]}-{email_nb_list[-1]}]")
                num_courriel_a_consulter = int(num_courriel_a_consulter)
                
                if num_courriel_a_consulter in email_nb_list:
                    return num_courriel_a_consulter
                
            except ValueError:
                print("Veuillez entrez un nombre entier.")


    def _send_email(self) -> None:
        """
        Demande à l'utilisateur respectivement:
        - l'adresse email du destinataire,
        - le sujet du message,
        - le corps du message.

        La saisie du corps se termine par un point seul sur une ligne.

        Transmet ces informations avec l'entête `EMAIL_SENDING`.
        """
        adresse_destinataire = input("Entrez l'adresse du destinataire: ")
        sujet = input("Entrez le sujet: ")
        contenu = input("Entrez le contenu du courriel, terminez la saisie avec un '.' seul sur une ligne:\n")

        ligne_contenu_supp = ""
        while (ligne_contenu_supp != "."):
            ligne_contenu_supp = input()
            contenu += "\n" + ligne_contenu_supp

        contenu = contenu[:-2] # On enlève le "\n." du string
        reponse_serveur = ""

        try:
            # Envoi au serveur
            send_email_payload: gloutils.EmailContentPayload = {"sender": self._username, "destination": adresse_destinataire, 
                                                                "date": gloutils.get_current_utc_time(), "subject": sujet, "content": contenu}
            
            message: gloutils.GloMessage = {"header": gloutils.Headers.EMAIL_SENDING.value, "payload":send_email_payload}

            # Vérifier si le serveur a bien reçu
            glosocket.snd_mesg(self._socket, str(message))
            reponse: gloutils.GloMessage = eval(glosocket.recv_mesg(self._socket))
            
            
            if reponse["header"] is gloutils.Headers.ERROR:
                reponse_serveur = "Le serveur a rencontré une erreur lors de la demande d'envoi de courriel."  
            else:
                reponse_serveur = "Le serveur a bien traité la demande d'envoi de courriel."
        except(glosocket.GLOSocketError):
            reponse_serveur = ("Le serveur a rencontré une erreur lors de la demande d'envoi de courriel.")
        
        print(reponse_serveur)

    def _check_stats(self) -> None:
        """
        Demande les statistiques au serveur avec l'entête `STATS_REQUEST`.

        Affiche les statistiques à l'aide du gabarit `STATS_DISPLAY`.
        """
        try:
            message: gloutils.GloMessage = {"header": gloutils.Headers.STATS_REQUEST.value}
        
            # Vérifier si le serveur a bien reçu
            glosocket.snd_mesg(self._socket, str(message))
            reponse: gloutils.GloMessage = eval(glosocket.recv_mesg(self._socket))

            if reponse["header"] is gloutils.Headers.ERROR:
                print("Le serveur a rencontré une erreur lors de la demande de statistiques.")
            else:
                print(gloutils.STATS_DISPLAY.format(**reponse["payload"]))

        except(glosocket.GLOSocketError):
            print("Le client n'a pas réussi à envoyer la requête de statistiques au serveur.")


    def _logout(self) -> None:
        """
        Préviens le serveur avec l'entête `AUTH_LOGOUT`.

        Met à jour l'attribut `_username`.
        """
        try:
            message: gloutils.GloMessage = {"header": gloutils.Headers.AUTH_LOGOUT.value}
            glosocket.snd_mesg(self._socket, str(message))

            reponse = eval(glosocket.recv_mesg(self._socket))

            if reponse["header"] is gloutils.Headers.ERROR:
                print("Il y a eu une erreur côté serveur lors du traitement de la déconnexion.")
            else:
                self._username = ""
        

        except(glosocket.GLOSocketError):
            print("Le client n'a pas réussi à envoyer la demande de déconnexion au serveur.")

    def run(self) -> None:
        """Point d'entrée du client."""
        should_quit = False

        while not should_quit:
            if not self._username:
                # Authentication menu
                option = input(f"{gloutils.CLIENT_AUTH_CHOICE}\nEntrez votre choix entre [1-3] : ")
            
                if option == "1": self._register()
                elif option == "2": self._login()
                elif option == "3": self._quit(); should_quit = True
                else: print("Veuillez entrer une des options suivantes sur votre clavier, puis la touche [Entrée] pour valider!")

            else:
                # Main menu
                option = input(f"{gloutils.CLIENT_USE_CHOICE}\nEntrez votre choix entre [1-4] : ")

                if option == "1": self._read_email()
                elif option == "2": self._send_email()
                elif option == "3": self._check_stats()
                elif option == "4": self._logout()
                else: print("Veuillez entrer une des options suivantes sur votre clavier, puis la touche [Entrée] pour valider!")

def _main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-d", "--destination", action="store",
                        dest="dest", required=True,
                        help="Adresse IP/URL du serveur.")
    args = parser.parse_args(sys.argv[1:])
    client = Client(args.dest)
    client.run()
    return 0


if __name__ == '__main__':
    sys.exit(_main())
