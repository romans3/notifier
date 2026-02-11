import hassapi as hass
import helpermodule as h
import re
import sys
import yaml
import ast
from datetime import timedelta


class Notifier_Dispatch(hass.Hass):

    def initialize(self):
        # Nome sensore e flag
        self.sensor = "sensor.centro_notifiche"
        self.sensor_pending = True
        self.sensor_retry_count = 0
        self.ticker_handle = None

        # Eventi del plugin HASS: crea il sensore quando il namespace è pronto
        self.listen_event(self._on_hass_plugin_started, "plugin_started", namespace="default")
        self.listen_event(self._on_hass_plugin_connected, "plugin_connected", namespace="default")

        # Fallback: ticker che prova a creare il sensore ogni 15s
        self.ticker_handle = self.run_every(
            self._sensor_ticker_try_create,
            self.datetime() + timedelta(seconds=10),
            15
        )

        # Args
        self.gh_tts_google_mode = self.args.get("gh_tts_google_mode")
        self.gh_switch_entity = self.args.get("gh_switch")
        self.gh_selected_media_player = self.args.get("gh_selected_media_player")
        self.alexa_switch_entity = self.args.get("alexa_switch")
        self.tts_language = self.args.get("tts_language")
        self.tts_period_of_day_volume = self.args.get("tts_period_of_day_volume")
        self.tts_dnd = self.args.get("dnd")
        self.text_notifications = self.args.get("text_notifications")
        self.screen_notifications = self.args.get("screen_notifications")
        self.speech_notifications = self.args.get("speech_notifications")
        self.phone_notifications = self.args.get("phone_notifications")
        self.html_mode = self.args.get("html_mode")
        self.text_notify = self.args.get("text_notify")
        self.phone_notify = self.args.get("phone_notify")
        self.priority_message = self.args.get("priority_message")
        self.guest_mode = self.args.get("guest_mode")
        self.persistent_notification_info = self.args.get("persistent_notification_info")
        self.location_tracker = self.args.get("location_tracker")
        self.personal_assistant_name = self.args.get("personal_assistant_name")
        self.phone_called_number = self.args.get("phone_called_number")

        # Secrets e manager
        config = self.get_plugin_config()
        config_dir = "/homeassistant"
        self.log(f"configuration dir: {config_dir}")
        secretsFile = config_dir + "/packages/secrets.yaml"
        with open(secretsFile, "r") as ymlfile:
            cfg = yaml.load(ymlfile, Loader=yaml.FullLoader)
        self.gh_tts = cfg.get("tts_google", "google_translate_say")
        self.gh_notify = cfg.get("notify_google", "google_assistant")
        self.phone_sip_server = cfg.get("sip_server_name", "fritz.box:5060")
        self.gh_tts_cloud = cfg.get("tts_google_cloud", "google_cloud")
        self.reverso_tts = cfg.get("reverso_tts", "reversotts.say")

        self.notification_manager = self.get_app("Notification_Manager")
        self.gh_manager = self.get_app("GH_Manager")
        self.alexa_manager = self.get_app("Alexa_Manager")
        self.phone_manager = self.get_app("Phone_Manager")

        self.listen_event(self.notify_hub, "hub")

    # ===== Event handlers del plugin HASS =====
    def _on_hass_plugin_started(self, event_name, data, kwargs):
        self.log("Plugin HASS 'started': creo centro_notifiche", level="INFO")
        self._create_sensor_now()

    def _on_hass_plugin_connected(self, event_name, data, kwargs):
        self.log("Plugin HASS 'connected': creo centro_notifiche", level="INFO")
        self._create_sensor_now()

    # ===== Creazione sensore sicura =====
    def _create_sensor_now(self):
        """Crea/aggiorna il sensore quando HASS è pronto; ferma il ticker."""
        try:
            self.set_state(
                self.sensor,
                state="ready",
                attributes={
                    "friendly_name": "Centro Notifiche",
                    "detail": "Sensore inizializzato"
                }
            )
            self.log("Sensore centro_notifiche creato/aggiornato (HASS pronto)", level="INFO")
            self.sensor_pending = False
            self.sensor_retry_count = 0
            if self.ticker_handle:
                self.cancel_timer(self.ticker_handle)
                self.ticker_handle = None
        except Exception as ex:
            # Ritenta una volta più tardi, senza loop aggressivo
            self.log(f"Creazione centro_notifiche fallita con HASS pronto: {ex}. Ritento tra 5s", level="WARNING")
            self.run_in(lambda kwargs: self._create_sensor_now(), 5)

    def _sensor_ticker_try_create(self, kwargs):
        """Fallback: prova a creare il sensore ogni 15s finché non riesce."""
        if not self.sensor_pending:
            if self.ticker_handle:
                self.cancel_timer(self.ticker_handle)
                self.ticker_handle = None
            return

        try:
            self.set_state(
                self.sensor,
                state="ready",
                attributes={
                    "friendly_name": "Centro Notifiche",
                    "detail": "Sensore inizializzato (ticker)"
                }
            )
            self.log("Sensore centro_notifiche creato via ticker", level="INFO")
            self.sensor_pending = False
            self.sensor_retry_count = 0
            if self.ticker_handle:
                self.cancel_timer(self.ticker_handle)
                self.ticker_handle = None
        except Exception as ex:
            self.sensor_retry_count += 1
            self.log(f"Creazione sensore fallita ({ex}). Tentativo #{self.sensor_retry_count}, riprovo tra 15s", level="WARNING")
            if self.sensor_retry_count in [3, 6]:
                self.log("HASS ancora non pronto: attendo senza forzare set_state", level="INFO")

    #####################################################################
    def check_flag(self, data):
        return str(data).lower() in ["1", "true", "on", "yes"]

    def check_location(self, data, location):
        return str(data).lower() == "" or str(data).lower() == location

    def check_notify(self, data):
        return False if (str(data).lower() in ["false", "off", "no"] or data == "0" or data == 0) else True

    def convert(self, lst):
        return {lst[1]: lst[3]}

    def createTTSdict(self, data) -> list:
        dizionario = ""
        flag = False  # default

        if data == "" or (not self.check_notify(data)):
            flag = False
        elif str(data).lower() in ["1", "true", "on", "yes"]:
            flag = True
            dizionario = {}
        else:
            # Caso OrderedDict serializzato
            if "OrderedDict([(" in str(data):
                dizionario = self.convert(list(data.split("'")))
                if dizionario.get("mode") is not None:
                    flag = self.check_flag(dizionario["mode"])
                else:
                    flag = True
            else:
                # Se è già un dict lo uso, altrimenti provo a valutare la stringa
                dizionario = data if isinstance(data, dict) else eval(data)
                if dizionario.get("mode") is not None:
                    flag = self.check_flag(dizionario["mode"])
                else:
                    flag = True

        return [flag, dizionario]

    def notify_hub(self, event_name, data, kwargs):
        self.log("#### START NOTIFIER_DISPATCH ####")

        # NORMALIZZAZIONE MESSAGE GLOBALE (prima di qualsiasi uso)
        raw_msg = data.get("message", "")

        if raw_msg is None:
            raw_msg = ""

        if not isinstance(raw_msg, str):
            raw_msg = str(raw_msg)

        # Rimuove righe vuote iniziali, spazi e newline
        normalized_msg = raw_msg.lstrip()

        # 🔥 Rimuove righe vuote interne (doppie o triple)
        normalized_msg = re.sub(r"\n\s*\n", "\n", normalized_msg)

        # Se dopo la normalizzazione è comunque vuoto → metti almeno uno spazio
        if not normalized_msg.strip():
            normalized_msg = " "

        data["message"] = normalized_msg

        # Creazione opportunistica del sensore: se è ancora pending, prova a crearlo ora
        if getattr(self, "sensor_pending", True):
            try:
                self.set_state(
                    self.sensor,
                    state="ready",
                    attributes={
                        "friendly_name": "Centro Notifiche",
                        "detail": "Sensore inizializzato (notify_hub)"
                    }
                )
                self.log("Sensore centro_notifiche creato dentro notify_hub", level="INFO")
                self.sensor_pending = False
                if hasattr(self, "ticker_handle") and self.ticker_handle:
                    self.cancel_timer(self.ticker_handle)
                    self.ticker_handle = None
            except Exception as ex:
                self.log(f"Creazione opportunistica sensore fallita: {ex}", level="WARNING")

        # Stati principali con default sicuri
        location_status = self.get_state(self.location_tracker) or "unknown"
        dnd_status = self.get_state(self.tts_dnd) or "unknown"
        guest_status = self.get_state(self.guest_mode) or "unknown"

        if location_status in ["unknown", None] or dnd_status in ["unknown", None] or guest_status in ["unknown", None]:
            self.log("Stati non pronti (location/dnd/guest), salto notify_hub", level="WARNING")
            return

        # Flag principali dal payload
        priority_flag = self.check_flag(data.get("priority", ""))
        noshow_flag = self.check_flag(data.get("no_show", ""))
        location_flag = self.check_location(data.get("location", ""), location_status)
        notify_flag = self.check_notify(data.get("notify", ""))

        # TTS dict di Google e Alexa
        google_flag, google = self.createTTSdict(data.get("google", "")) if data.get("google") else (False, {})
        alexa_flag, alexa = self.createTTSdict(data.get("alexa", "")) if data.get("alexa") else (False, {})

        # INPUT BOOLEAN
        priority_status = (self.get_state(self.priority_message) == "on") or priority_flag

        # INPUT SELECT
        notify_name = self.get_state(self.text_notify) or ""
        phone_notify_name = self.get_state(self.phone_notify) or ""

        # NOTIFICATION
        if priority_status:
            useNotification = True
        elif self.get_state(self.text_notifications) == "on" and data.get("message", "") != "" and notify_flag and location_flag:
            useNotification = True
        else:
            useNotification = False

        # PERSISTENT
        if priority_status:
            usePersistentNotification = True
        elif self.get_state(self.screen_notifications) == "on" and data.get("message", "") != "" and not noshow_flag:
            usePersistentNotification = True
        else:
            usePersistentNotification = False

        # TTS
        if priority_status:
            useTTS = True
        elif self.get_state(self.speech_notifications) == "on" and dnd_status == "off" and (location_status == "home" or guest_status == "on"):
            useTTS = True
        else:
            useTTS = False

        # PHONE
        if priority_status:
            usePhone = True
        elif self.get_state(self.phone_notifications) == "on" and data.get("message", "") != "" and dnd_status == "off":
            usePhone = True
        else:
            usePhone = False

        # TTS switch e normalizzazione servizio Google
        gh_switch = self.get_state(self.gh_switch_entity)
        alexa_switch = self.get_state(self.alexa_switch_entity)

        gh_mode_state = self.get_state(self.gh_tts_google_mode)
        if gh_mode_state is not None:
            gh_mode_lower = str(gh_mode_state).lower()
            if gh_mode_lower == "reverso":
                gh_notifica = self.reverso_tts
            elif gh_mode_lower == "google cloud":
                gh_notifica = self.gh_tts_cloud
            elif gh_mode_lower == "google say":
                gh_notifica = self.gh_tts
            else:
                gh_notifica = self.gh_notify
        else:
            gh_notifica = self.gh_notify

        # FROM SCRIPT_NOTIFY: completa i campi mancanti
        if data.get("called_number", "") == "":
            data.update({"called_number": self.get_state(self.phone_called_number) or ""})
        if data.get("html", "") == "":
            data.update({"html": self.get_state(self.html_mode) or ""})

        # PERSISTENT
        if usePersistentNotification:
            try:
                self.notification_manager.send_persistent(data, self.persistent_notification_info)
            except Exception as ex:
                self.log(f"An error occurred in persistent notification: {ex}", level="ERROR")
                try:
                    self.set_state(self.sensor, state=f"Error in Persistent Notification: {ex}")
                except Exception:
                    pass
                self.log(sys.exc_info())

        # TEXT NOTIFICATION
        if useNotification:
            try:
                self.notification_manager.send_notify(data, notify_name, self.get_state(self.personal_assistant_name))
            except Exception as ex:
                self.log(f"An error occurred in text-telegram notification: {ex}", level="ERROR")
                try:
                    self.set_state(self.sensor, state=f"Error in Text Notification: {ex}")
                except Exception:
                    pass
                self.log(sys.exc_info())

        # --- IMAGE NOTIFICATION (notify.telegram) - stile originale, con nome assistente dinamico ---
        if "image" in data and data["image"]:
            try:
                # Nome assistente dinamico (es. Jarvis, Pippo, ecc.)
                assistant_name = self.get_state(self.personal_assistant_name) or ""
                now = self.datetime().strftime("%H:%M:%S")

                # TITOLO: se lo passa lo script, usiamo quello; altrimenti costruiamo [Assistente - HH:MM:SS]
                title = data.get("title", "")
                if not title or title.strip() == "":
                    if assistant_name:
                        title = f"[{assistant_name} - {now}]"
                    else:
                        title = f"[{now}]"

                # MESSAGGIO: prendiamo quello passato dallo script, sapendo che non è mai vuoto (messo in sicurezza sopra)
                msg = data.get("message", " ")
                if not msg or msg.strip() == "":
                    msg = " "

                # Messaggio finale nello stile originale: titolo in grassetto + newline + testo
                final_message = f"*{title}*\n{msg}"

                self.log(f"Invio immagine via notify.telegram: {data['image']}", level="INFO")

                self.call_service(
                    "notify/telegram",
                    message=final_message,
                    data={
                        "photo": data["image"],
                        "caption": final_message,  # caption sotto la foto
                    }
                )

            except Exception as ex:
                self.log(f"Errore invio immagine notify.telegram: {ex}", level="ERROR")

        # TTS
        if useTTS:
            # GOOGLE
            if gh_switch == "on" and google_flag:
                if data.get("google", "") != "":
                    if "media_player" not in google:
                        google["media_player"] = self.get_state(self.gh_selected_media_player)
                    if "volume" not in google:
                        # usa tts_period_of_day_volume come percentuale [0-100]
                        vol_pct = self.get_state(self.tts_period_of_day_volume) or 100
                        try:
                            google["volume"] = float(vol_pct) / 100.0
                        except Exception:
                            google["volume"] = 1.0
                    if "media_content_id" not in google:
                        google["media_content_id"] = ""
                    if "media_content_type" not in google:
                        google["media_content_type"] = ""
                    if "message_tts" not in google:
                        google["message_tts"] = data.get("message", "")
                    if "language" not in google:
                        lang = self.get_state(self.tts_language) or "it"
                        google["language"] = str(lang).lower()
                try:
                    self.gh_manager.speak(google, gh_mode_state, gh_notifica)
                except Exception as ex:
                    self.log(f"Errore in GH TTS: {ex}", level="ERROR")

        # ALEXA
        if alexa_switch == "on" and alexa_flag:
            if data.get("alexa", "") != "":
                if "message_tts" not in alexa:
                    alexa["message_tts"] = data.get("message", "")
                if "title" not in alexa:
                    alexa["title"] = data.get("title", "")
                if "volume" not in alexa:
                    vol_pct = self.get_state(self.tts_period_of_day_volume) or 100
                    try:
                        alexa["volume"] = float(vol_pct) / 100.0
                    except Exception:
                        alexa["volume"] = 1.0
                if "language" not in alexa:
                    alexa["language"] = self.get_state(self.tts_language) or "it"

            try:
                # Prova a usare Alexa Media
                self.alexa_manager.speak(alexa)
            except Exception as ex:
                self.log(f"Alexa Media non disponibile: {ex}. Uso notify.send_message come fallback", level="WARNING")
                try:
                    # Fallback: invia comunque il messaggio con notify.send_message
                    self.call_service(
                        "notify/send_message",
                        message=alexa.get("message_tts", data.get("message", "")),
                        title=alexa.get("title", "Interfono")
                    )
                except Exception as ex2:
                    self.log(f"Errore anche in notify.send_message: {ex2}", level="ERROR")

        # PHONE
        if usePhone:
            try:
                language = self.get_state(self.tts_language) or "it"
                self.phone_manager.send_voice_call(data, phone_notify_name, self.phone_sip_server, language)
            except Exception as ex:
                self.log(f"An error occurred in phone notification: {ex}", level="ERROR")
                try:
                    self.set_state(self.sensor, state=f"Error in Phone Notification: {ex}")
                except Exception:
                    pass
                self.log(sys.exc_info())

        # Ripristino del priority a OFF in modo sicuro
        try:
            if self.get_state(self.priority_message) == "on":
                self.set_state(self.priority_message, state="off")
        except Exception:
            pass
            