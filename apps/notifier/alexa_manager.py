import hassapi as hass
from datetime import datetime
import re
import sys
import time
from queue import Queue
from threading import Thread

"""
    Class Alexa Manager handles sending text to speech messages to Alexa media players
    Following features are implemented:
    - Speak text to choosen media_player
    - Full queue support to manage async multiple TTS commands
    - Full wait to tts to finish to be able to supply a callback method
"""

NOTIFY = "notify/"

SUB_VOICE = [
    # (r"[.]{2,}", r"."),
    (r"[\?\.\!,]+(?=[\?\.\!,])", r""),  # Exclude duplicate
    (r"(\s+\.|\s+\.\s+|[\.])(?! )(?![^{]*})(?![^\d.]*\d)", r". "),
    (r"&", r" and "),  # escape
    # (r"(?<!\d),(?!\d)", r", "),
    (r"[\n\*]", r" "),
    (r" +", r" "),
]

SUB_TEXT = [(r" +", r" "), (r"\s\s+", r"\n")]

VOICE_NAMES = (
    "Carla",
    "Giorgio",
    "Bianca",
    "Ivy",
    "Joanna",
    "Joey",
    "Justin",
    "Kendra",
    "Kimberly",
    "Matthew",
    "Salli",
    "Nicole",
    "Russell",
    "Amy",
    "Brian",
    "Emma",
    "Aditi",
    "Raveena",
    "Chantal",
    "Celine",
    "Lea",
    "Mathieu",
    "Hans",
    "Marlene",
    "Vicki",
    "Aditi",
    "Mizuki",
    "Takumi",
    "Vitoria",
    "Camila",
    "Ricardo",
    "Penelope",
    "Lupe",
    "Miguel",
    "Conchita",
    "Enrique",
    "Lucia",
    "Mia",
)

SUPPORTED_LANGUAGES = [
    "it-IT",
    "en-US",
    "en-CA",
    "en-AU",
    "en-GB",
    "en-IN",
    "fr-CA",
    "fr-FR",
    "de-DE",
    "hi-IN",
    "ja-JP",
    "pt-BR",
    "es-US",
    "es-ES",
    "es-MX",
]

SPEECHCON = [
    "a ah",
    "abracadabra",
    "accidenti",
    "accipicchia",
    "addio",
    "ah",
    "ahi",
    "ahia",
    "alleluia",
    "aloha",
    "alè",
    "anzi",
    "apriti sesamo",
    "argh",
    "arrivederci",
    "attenzione",
    "auguri",
    "badabim badabum",
    "badabum",
    "bah",
    "bam",
    "bang",
    "bang bang",
    "banzai",
    "basta",
    "batti cinque",
    "bau",
    "bazinga",
    "beh",
    "ben fatto",
    "bene",
    "bene bene",
    "bim bum bam",
    "bing",
    "bingo",
    "bip bip",
    "bis",
    "bla",
    "bla bla bla",
    "bleah",
    "boh",
    "boing",
    "bravo",
    "brrr",
    "bum",
    "buon appetito",
    "buon viaggio",
    "buona fortuna",
    "buonanotte",
    "buonasera",
    "buongiorno",
    "buu",
    "capito",
    "caspita",
    "cavoli",
    "cavolo",
    "cawabanga",
    "certo",
    "chissà",
    "ci stai",
    "ciao",
    "cioè",
    "ciuf ciuf",
    "clic clac",
    "come desideri",
    "come no",
    "come non detto",
    "come va",
    "come vuoi",
    "contaci",
    "coraggio",
    "così così",
    "cucù",
    "d'accordo",
    "d'oh",
    "dai",
    "davvero",
    "din don",
    "ding",
    "ding ding ding",
    "dormi bene",
    "eh",
    "eh beh",
    "eh già",
    "ehm",
    "etciù",
    "eureka",
    "evviva",
    "fiuu",
    "geronimo",
    "giusto",
    "già",
    "grande giove",
    "grazie",
    "ha",
    "hey",
    "hip hip hurrà",
    "hmm",
    "hurrà",
    "hué hué",
    "in guardia",
    "incantata",
    "kabùm",
    "ma dai",
    "magari",
    "mah",
    "mamma mia",
    "mi piace",
    "miao",
    "mistero",
    "muu",
    "nano nano",
    "non mi dire",
    "oh",
    "oh no",
    "oh oh",
    "oh sì",
    "oh yes",
    "oi",
    "oink",
    "ok",
    "okei",
    "oooh",
    "or ora",
    "ping",
    "più o meno",
    "plop",
    "pop",
    "poti poti",
    "puf",
    "pum pum",
    "puntini puntini",
    "puoi scommetterci",
    "qua qua",
    "ricevuto",
    "roger",
    "salute",
    "scacco matto",
    "scherzavo",
    "sogni d'oro",
    "splash",
    "spoiler alert",
    "su ",
    "su su",
    "swish",
    "ta dà",
    "taac",
    "tic tac",
    "tic tic tic",
    "tic-toc",
    "toc toc",
    "toh",
    "touché",
    "trallalà",
    "tsk tsk",
    "tump",
    "tweet",
    "uffa",
    "uh la là",
    "uh oh",
    "uomo in mare",
    "vabbè",
    "voilà",
    "vroom",
    "wow",
    "yippii",
    "zac",
    "zap",
]

MOBILE_PUSH = ["push", "dropin", "dropin_notification"]


class Alexa_Manager(hass.Hass):
    def initialize(self) -> None:
        # self.set_log_level("DEBUG")
        self.alexa_service = self.args.get("alexa_service")
        # self.alexa_switch_entity = self.args.get("alexa_switch")
        self.alexa_select_media_player = self.args.get("alexa_select_media_player")
        self.alexa_type = self.args.get("alexa_type")
        self.alexa_method = self.args.get("alexa_method")
        self.alexa_sensor_media_player = self.args.get("alexa_sensor_media_player")
        self.alexa_voice = self.args.get("alexa_voice")
        # self.alexa_language = self.args.get("alexa_language")
        self.prosody = self.args.get("prosody")
        self.wait_time = self.args.get("wait_time")
        self.cehck_alexa_service = self._check_alexa(self.alexa_service)

        # listener per sincronizzare il volume quando cambia
        self.listen_state(self.sync_volume, "sensor.period_of_day_volume")

        self.queue = Queue(maxsize=0)
        self._when_tts_done_callback_queue = Queue()

        t = Thread(target=self.worker)
        t.daemon = True
        t.start()

    def safe_log(self, message: str, level: str = "INFO"):
        """
        Logga un messaggio mantenendo accenti e simboli, sostituendo solo quelli non validi.
        """
        try:
            clean_msg = str(message).encode("utf-8", "replace").decode("utf-8")
            self.log(clean_msg, level=level)
        except Exception as ex:
            self.log(f"[safe_log error] {ex} - original: {message}", level="ERROR")

    def sync_volume(self, entity, attribute, old, new, kwargs):
        try:
            # leggi il volume normalizzato dal sensore
            volume = float(self.get_state(entity, attribute="vol"))

            # recupera i media player Alexa attivi
            alexa_players = self.player_get(self.get_state(self.alexa_sensor_media_player))

            # imposta il volume su ciascun player
            if alexa_players:
                for player in alexa_players:
                    self.call_service("media_player/volume_set", entity_id=player, volume_level=volume)

            # log
            self.log(f"Volume Alexa sincronizzato a {volume}", level="INFO")

        except Exception as ex:
            self.log(f"Errore sincronizzando volume Alexa: {ex}", level="ERROR")

    def speak(self, alexa):
        """Speak the provided text through the media player."""
        if not self.cehck_alexa_service:
            # Alexa Media non ancora pronto → stato waiting
            self.set_state(
                "sensor.centro_notifiche",
                state="waiting",
                attributes={
                    "friendly_name": "Centro Notifiche",
                    "detail": "Alexa Media non ancora pronto",
                    "doc_url": "https://github.com/custom-components/alexa_media_player"
                }
            )
            self.log("Alexa Media non trovato, salto speak()", level="WARNING")
            return

        self.lg(f"-------------------- ALEXA START DISPATCH --------------------")
        self.lg(f"FROM DISPATCH: {type(alexa)} value {alexa}")

        # Rimuovi chiavi con valori None o vuoti
        alexa = {k: v for k, v in alexa.items() if v not in [None, "None", ""]}

        # Normalizza il notifier
        notifier = str(alexa.get("notifier", self.alexa_service))

        if notifier == "alexa_media":
            selected = self.get_state(self.alexa_select_media_player)

            if selected:
                # converte la friendly name in formato servizio
                slug = (
                    selected.lower()
                    .replace(" ", "_")
                    .replace("'", "")
                )
                notifier = f"{self.alexa_service}_{slug}"
            else:
                notifier = f"{self.alexa_service}_last_called"

        alexa["notifier"] = notifier

        self.lg(f"REMOVE [NONE] VALUE: {type(alexa)} value {alexa}")

        # Volume e messaggio
        default_restore_volume = float(self.get_state(self.args.get("default_restore_volume"))) / 100
        volume = float(alexa.get("volume", default_restore_volume))
        message = str(alexa.get("message", alexa.get("message_tts", "")))

        # 🔔 Notifica sincronizzazione volume
        try:
            vol_sensor = self.get_state("sensor.period_of_day_volume", attribute="vol")
            self.log(f"Volume Alexa sincronizzato a {vol_sensor}", level="INFO")
        except Exception as ex:
            self.log(f"Errore leggendo volume Alexa: {ex}", level="ERROR")

        # Player e tipo
        alexa_player = self.player_get(alexa.get("media_player", self.get_state(self.alexa_sensor_media_player)))
        alexa_type = (
            str(alexa.get("type", self.get_state(self.alexa_type))).lower().replace("dropin", "dropin_notification")
        )

        # Aggiorna il sensore come 'ready' con dettagli e attributi extra
        try:
            self.set_state(
                "sensor.centro_notifiche",
                state="ready",
                attributes={
                    "friendly_name": "Centro Notifiche",
                    "detail": f"Messaggio inviato a {alexa_player}",
                    "volume": volume,
                    "message": message,
                    "type": alexa_type,
                    "notifier": notifier,
                    # attributi extra per Lovelace
                    "last_message": message,
                    "last_target": alexa_player,
                    "last_volume": volume,
                    "last_update": datetime.now().strftime("%d.%m.%Y - %H:%M:%S")
                }
            )
            self.log(f"Messaggio Alexa inviato a {alexa_player}", level="INFO")
        except Exception as ex:
            self.log(f"Errore aggiornando centro_notifiche: {ex}", level="ERROR")

        # Qui continua la tua logica originale di invio TTS...


        # Push notification
        push = bool(self.check_bool(alexa.get("push")))
        if push or alexa_type in MOBILE_PUSH and message:
            message_push = self.remove_tags(self.replace_regular(message, SUB_TEXT))
            msg = message_push if message_push else " "
            service = NOTIFY + alexa["notifier"]

            payload = {
                "type": "push" if push else alexa_type,
                "title": str(alexa.get("title", "")),
            }
            # target solo se usi last_called
            if alexa["notifier"].endswith("last_called"):
                payload["target"] = [alexa_player[0]]

            self.call_service(service, message=msg, data=payload)
            self.lg(f"PUSH: {push} - TYPE: {alexa_type} - MESSAGE: {message_push}")
        # Media Content # TODO Restore volume??
        media_content_id = alexa.get("media_content_id")
        media_content_type = alexa.get("media_content_type")
        if media_content_id:
            self.volume_get(alexa_player, default_restore_volume)
            self.volume_set(alexa_player, volume)
            self.call_service(
                "media_player/play_media",
                entity_id=alexa_player,
                media_content_id=media_content_id,
                media_content_type=media_content_type,
                # extra = {"timer": 10} ##??
            )
            self.lg(f"Content id: {media_content_id} - Content type: {media_content_type}")
        # Queues the message to be handled async, use when_tts_done_do method to supply callback when tts is done

        elif alexa_type not in MOBILE_PUSH and message:
            self.queue.put(
                {
                    "text": message,
                    "volume": volume,
                    "alexa_type": alexa_type,
                    "alexa_player": alexa_player,  # media_player
                    "default_restore_volume": default_restore_volume,
                    "alexa_notifier": notifier,  # uso il notifier già normalizzato sopra
                    "wait_time": float(alexa.get("wait_time", self.get_state(self.wait_time))),
                    "language": alexa.get("language"),  # self.get_state(self.alexa_language)),
                    "alexa_method": str(alexa.get("method", self.get_state(self.alexa_method)).lower()),
                    "alexa_voice": str(alexa.get("voice", self.get_state(self.alexa_voice))).capitalize(),
                    "alexa_audio": alexa.get("audio", None),
                    "rate": float(alexa.get("rate", self.get_state(self.prosody["rate"]))),
                    "pitch": float(alexa.get("pitch", self.get_state(self.prosody["pitch"]))),
                    "ssml_volume": float(alexa.get("ssml_volume", self.get_state(self.prosody["volume"]))),
                    "whisper": bool(self.check_bool(alexa.get("whisper", False))),
                    "ssml_switch": bool(self.check_bool(alexa.get("ssml", self.get_state(self.args["ssml_switch"])))),
                }
            )
        self.lg(f"-------------------- ALEXA  END  DISPATCH --------------------")

    def lg(self, message):
        self.log(message, level="DEBUG", ascii_encode=False)

    def check_bool(self, value):
        return str(value).lower() in ["true", "on", "yes", "1"]

    def inbetween(self, minv, value, maxv):
        return sorted([minv, value, maxv])[1]

    def speak_tag(self, value):  # TODO tags
        return value if "<speak>" in value or not "</" in value else f"<speak>{value}</speak>"

    def effect_tag(self, value):
        return f"<amazon:effect name='whispered'>{value}</amazon:effect>"

    def prosody_tag(self, value, rate, pitch, volume):
        if rate != 100.0 or pitch != 0.0 or volume != 0.0:
            rate = f"{self.inbetween(20, rate, 200)}%"  # min 20% max 200%
            pitch = f"{self.inbetween(-33.3, pitch, 50):+g}%"  # min -33.3 max +50
            volume = f"{self.inbetween(-50, volume, 4.08):+g}dB"  # max +4.08dB
            return f"<prosody rate='{rate}' pitch='{pitch}' volume='{volume}'> {value} </prosody>"
        return value

    def audio_tag(self, value: None):
        if value is None:
            return ""
        return f"<audio src='{value}'/>" if "<audio src=" not in value else value

    def lang_tag(self, value, lang):
        if lang not in SUPPORTED_LANGUAGES:
            self.lg(f"NOT SUPPORTED LANGUAGE: {lang}")
            return value
        self.lg(f"OK ADDED SSML LANGUAGE: {lang}")
        return f"<lang xml:lang='{lang}'>{value}</lang>"

    def voice_tag(self, value, name):
        if name not in VOICE_NAMES:
            self.lg(f"NOT SUPPORTED VOICE: {name}")
            return value
        self.lg(f"OK ADDED VOICE: {name}")
        return f"<voice name='{name}'>{value}</voice>"

    def say_as_tag(self, value):
        return f"<say-as interpret-as='interjection'>{value}</say-as>"

    def find_speechcon(self, value):
        substrings = sorted(SPEECHCON, key=len, reverse=True)
        regex = re.compile(r"\b" + r"\b|\b".join(map(re.escape, substrings)), re.I)
        regex_match = re.findall(regex, value)
        self.lg(f"FOUND SPEECHCON: {len(regex_match)} -> {regex_match}")
        return regex.sub(lambda m: self.say_as_tag(m.group()), value)

    def player_get(self, user_player):
        media_player = []
        user_player = user_player if isinstance(user_player, list) else self.converti(str(user_player.lower()))
        for mpu in user_player:  # MediaPlayerUser
            if "test" in mpu:
                media_player.extend(self.player_alexa)
            if not self.entity_exists(mpu):
                mpu = self.dict_select.get(mpu)
            if mpu:
                if "group." in mpu:
                    media_player.extend(self.get_state(mpu, attribute="entity_id"))
                elif "sensor." in mpu:
                    media_player.append(self.get_state(mpu))
                elif "media_player." in mpu:
                    media_player.append(mpu)
                else:
                    self.log(f"Invalid group, sensor or player ENTITY-ID ({mpu})", level="WARNING")
        if not media_player:
            # media_player.append(self.get_state(self.alexa_sensor_media_player))
            media_player = self.player_alexa
            self.log(f"No media player {user_player} found. I use the default one. ({media_player})", level="WARNING")
        media_player = list(set(media_player))
        self.lg(f"GET PLAYER: {media_player}")
        return media_player

    def volume_get(self, media_player, volume: float):
        """Get and save the volume of each media player."""
        self.dict_volumes = {m: self.get_state(m, attribute="volume_level", default=volume) for m in media_player}
        self.lg(f"GET VOLUMES: {self.dict_volumes}")
        return self.dict_volumes

    def volume_set(self, media_player, volume: float, **restore: False):
        if self.dict_volumes:
            for i, j in self.dict_volumes.items():
                if j != volume:
                    if restore:
                        self.call_service("media_player/volume_set", entity_id=i, volume_level=j)
                        time.sleep(1)
                        self.lg(f"OK RESTORE VOL: {i} {j} [State: {self.get_state(i, attribute='volume_level')}]")
                    else:
                        self.call_service("media_player/volume_set", entity_id=media_player, volume_level=volume)
                        self.lg(f"SET VOLUMES: {media_player} {volume}")
                        break  # time.sleep(2)

    def replace_char(self, text: str, substitutions: dict):
        """Function that does multiple string replace ops in a single pass."""
        substrings = sorted(substitutions, key=len, reverse=True)
        regex = re.compile(r"\b" + r"\b|\b".join(map(re.escape, substrings)), re.I)  # r'\b%s\b' % r'\b|\b'
        return regex.sub(lambda match: substitutions[str.lower(match.group(0))], text)  # added str.lower()

    def replace_regular(self, text: str, substitutions: list):
        for old, new in substitutions:
            regex = re.compile(old)
            text = re.sub(regex, new, str(text).strip())
        return text

    def remove_tags(self, text: str):
        """Remove all tags from a string."""
        regex = re.compile(r"<.*?>")
        return re.sub(regex, "", str(text).strip())

    def converti(self, stringa) -> list:
        regex = re.compile(r"\s*,\s*")
        return self.split_device_list(re.sub(regex, ",", stringa))

    def has_numbers(self, string):
        numbers = re.compile(r"\d{4,}|\d{3,}\.\d")
        return numbers.search(string)

    def set_sensor(self, state, error):
        attributes = {}
        attributes["icon"] = "mdi:amazon-alexa"
        attributes["Error"] = error
        self.set_state("sensor.centro_notifiche", state=state, attributes=attributes)

    def when_tts_done_do(self, callback: callable) -> None:
        """Callback when the queue of tts messages are done."""
        self._when_tts_done_callback_queue.put(callback)

    def worker(self):
        while True:
            try:
                data = self.queue.get()
                self.lg(f"WORKER: {type(data)} value {data}")
                alexa_player = data["alexa_player"]
                self.volume_get(alexa_player, data["default_restore_volume"])
                self.volume_set(alexa_player, data["volume"])

                # Replace and clean message
                message_clean = self.replace_regular(data["text"], SUB_VOICE)
                self.lg(f"INPUT MESSAGE: {data['text']}")
                self.lg(f"MESSAGE CLEAN: {message_clean}")

                # Speech time calculator
                # words = len(message_clean.split())
                # chars = message_clean.count("")
                words = len(self.remove_tags(message_clean).split())
                chars = self.remove_tags(message_clean).count("")
                duration = (words * 0.007) * 60

                # Extra time
                if self.has_numbers(message_clean):
                    data["wait_time"] += 4
                    self.lg(f"OK NUMBER! ADDED EXTRA TIME: {data['wait_time']}")
                if (chars / words) > 7 and chars > 90 or data["alexa_audio"] is not None:
                    data["wait_time"] += 7
                    self.lg(f"OK ADDED EXTRA TIME: {data['wait_time']}")
                # Alexa type-method
                if "tts" in data["alexa_type"]:
                    alexa_data = {"type": "tts"}
                else:
                    data["wait_time"] += 1.5
                    alexa_data = {
                        "type": data["alexa_type"],
                        "method": data["alexa_method"],
                    }
                # TAGS SSML
                if data["ssml_switch"] and not "<speak>" in message_clean:
                    voice = "Alexa" if data["alexa_voice"] not in VOICE_NAMES else data["alexa_voice"]
                    whisper = data["whisper"]
                    if "Alexa" in voice and not whisper:
                        message_clean = self.find_speechcon(message_clean)
                    message_clean = self.lang_tag(message_clean, data["language"])
                    if "Alexa" not in voice:
                        message_clean = self.voice_tag(message_clean, voice)
                    message_clean = self.audio_tag(data["alexa_audio"]) + message_clean
                    message_clean = self.prosody_tag(message_clean, data["rate"], data["pitch"], data["ssml_volume"])
                    # -->
                    rate = self.inbetween(20, data["rate"], 200)  # TODO
                    if rate < 100:
                        duration += (100 - rate) * (duration / 100)
                    elif rate > 100:
                        duration /= 2
                    # -->
                    if whisper:
                        message_clean = self.effect_tag(message_clean)
                    if "tts" in data["alexa_type"]:
                        message_clean = self.speak_tag(message_clean)
                    self.lg(f"OK SSML TAGS: {message_clean}")
                # Estimate reading time
                duration += data["wait_time"]
                self.lg(f"DURATION-WAIT: {duration} - words: {words} - Chars: {chars}")

                # Speak >>>
                msg = message_clean.strip() if message_clean else " "

                # Normalizza il notifier
                notifier = data["alexa_notifier"]

                if notifier == "alexa_media":
                    # prova a leggere il dispositivo scelto dall'utente (friendly name)
                    selected = self.get_state(self.alexa_select_media_player)

                    if selected:
                        # converte la friendly name in formato servizio:
                        # "Echo Show di Giuseppe" -> "echo_show_di_giuseppe"
                        slug = (
                            selected.lower()
                            .replace(" ", "_")
                            .replace("'", "")
                        )
                        notifier = f"{self.alexa_service}_{slug}"
                    else:
                        # fallback universale
                        notifier = f"{self.alexa_service}_last_called"

                service = NOTIFY + notifier

                # prepara payload
                payload = {
                    "type": alexa_data.get("type"),
                }
                if alexa_data.get("method"):
                    payload["method"] = alexa_data.get("method")

                # target solo se usi last_called
                if notifier.endswith("last_called"):
                    payload["target"] = data["alexa_player"]

                # chiamata al servizio
                self.call_service(service, message=msg, data=payload)

                time.sleep(duration if duration > 0 else 0)

                # Restore volume
                self.volume_set(alexa_player, data["volume"], restore=True)
            except Exception as ex:
                self.log("An error occurred in Alexa Manager (worker): {}".format(ex), level="ERROR")
                self.log(f"DATA: {data}", level="ERROR")
                self.set_sensor("Alexa Manager - Worker Error ", ex)
            self.queue.task_done()

            if self.queue.qsize() == 0:

                try:
                    while self._when_tts_done_callback_queue.qsize() > 0:
                        callback_func = self._when_tts_done_callback_queue.get_nowait()
                        callback_func()  # Call the callback
                        self._when_tts_done_callback_queue.task_done()
                except:
                    self.log("Errore nel CallBack", level="ERROR")
                    self.set_sensor("Alexa Manager - CallBack Error ", ex)
                    pass  # Nothing in queue
            self.lg("---------------------------------------------------------\n")

    def _check_alexa(self, service):
        """Get the media players from the alexa_media service in Home Assistant."""
        hass_config = self.get_plugin_config()

        # Assicurati che sia un dict
        if not isinstance(hass_config, dict):
            self.log("hass_config non è un dict valido (HA non ancora pronto)", level="WARNING")
            return []

        # Usa .get() per evitare KeyError
        components = hass_config.get("components", [])
        if not components:
            self.log("Chiave 'components' non trovata in hass_config", level="WARNING")
            return []

        if service in components:
            exclude = [service, "this_device", "_apps"]

            # Trova servizi alexa_media
            cehck_alexa = [
                s["service"]
                for s in self.list_services(namespace="default")
                if "notify" in s.get("domain", "") and service in s.get("service", "")
            ]
            self.lg(f"OK, Service: {cehck_alexa}")

            # Se non trova nulla → stato waiting + retry
            if not cehck_alexa:
                self.set_state(
                    "sensor.centro_notifiche",
                    state="waiting",
                    attributes={
                        "friendly_name": "Centro Notifiche",
                        "detail": "Alexa Media non ancora pronto"
                    }
                )
                self.log("Alexa Media non trovato, riprovo tra 10s", level="WARNING")
                self.run_in(lambda kwargs: self._check_alexa(service), 10)
                return []

            # Converti in media_player
            service_replace = [
                mp.replace("alexa_media_", "media_player.") for mp in cehck_alexa if mp != "alexa_media"
            ]
            self.lg(f"OK, Entity: {service_replace}")

            # Filtra lista exclude
            self.player_alexa = [
                s for s in service_replace if self.entity_exists(s) and not any(player in s for player in exclude)
            ]
            self.lg(f"OK, found the Alexa Media component. List of media players: {self.player_alexa}")

            # Friendly names
            names = [self.friendly_name(name) for name in self.player_alexa]
            self.lg(f"FRIENDLY_NAME: {names}")

            # Recupera le opzioni dall'input_select
            selectoptions = self.get_state(self.alexa_select_media_player, attribute="options")
            if not selectoptions or not isinstance(selectoptions, list):
                self.log("Input select non pronto o non valido", level="WARNING")
                selectoptions = []
            self.lg(f"INPUT SELECT OPTIONS: {selectoptions} - TYPE: {type(selectoptions)}")

            check_alexa_options = [x for x in self.player_alexa if self.friendly_name(x) in selectoptions]
            self.lg(f"ENTITY_ID MEDIA_PLAYER IN INPUT SELECTS {check_alexa_options}")

            # Conversione friendly name → entity id
            all_state = self.get_state()
            self.list_select = []
            self.dict_select = {}
            if all_state and isinstance(all_state, dict):
                for entity, state in all_state.items():
                    try:
                        domain, name = entity.split(".")
                    except ValueError:
                        continue
                    friendly_name = state.get("attributes", {}).get("friendly_name")
                    if domain in ["media_player", "group", "sensor"] and friendly_name in selectoptions:
                        self.list_select.append(entity)
                        for select in selectoptions:
                            if select.lower() == friendly_name.lower():
                                self.dict_select[friendly_name.lower()] = entity
            else:
                self.log("Stati non disponibili al momento, salto la conversione", level="WARNING")

            self.lg(f"LIST ENTITY_ID SELECT OPTIONS: {self.list_select}")
            self.lg(f"DICTIONARY NAME-ENTITY_ID: {self.dict_select}")

            # Se arriviamo qui Alexa Media è pronto → aggiorna sensore con attributi
            self.set_state(
                "sensor.centro_notifiche",
                state="ready",
                attributes={
                    "friendly_name": "Centro Notifiche",
                    "alexa_players": self.player_alexa,
                    "friendly_names": names,
                    "select_options": selectoptions,
                    "dict_select": self.dict_select
                }
            )
            self.log("Sensore centro_notifiche aggiornato con info Alexa", level="INFO")

            return cehck_alexa

        self.log("Alexa Media component non trovato nei components", level="ERROR")
        return []
