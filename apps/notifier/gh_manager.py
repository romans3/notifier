import hassapi as hass
import helpermodule as h
import time
import datetime
import re
import sys
from queue import Queue
from threading import Thread
from datetime import datetime

#from threading import Event

"""
Class TTS Manager handles sending text to speech messages to media players
Following features are implemented:
- Speak text to choosen media_player
- Full queue support to manage async multiple TTS commands
- Full wait to tts to finish to be able to supply a callback method
"""

__NOTIFY__ = "notify/"
__TTS__ = "tts/"
SUB_TTS = [(r"[\*\-\[\]_\(\)\{\~\|\}\s]+",r" ")]
SUB_VOICE = [
    # (r"[.]{2,}", r"."),
    (r"[\?\.\!,]+(?=[\?\.\!,])", r""),  # Exclude duplicate
    (r"(\s+\.|\s+\.\s+|[\.])(?! )(?![^{]*})(?![^\d.]*\d)", r". "),
    (r"&", r" and "),  # escape
    # (r"(?<!\d),(?!\d)", r", "),
    (r"[\n\*]", r" "),
    (r" +", r" "),
]

class GH_Manager(hass.Hass):

    def initialize(self) -> None:
        self.gh_wait_time = self.args["gh_wait_time"]
        self.gh_select_media_player = self.args["gh_select_media_player"]
        self.ytube_player = self.args["gh_select_media_player"]
        self.ytube_called = False

        self.tts_period_of_day_volume = self.args.get("tts_period_of_day_volume")

        if self.tts_period_of_day_volume:
            self.listen_state(self.sync_volume, self.tts_period_of_day_volume)

        self.queue = Queue(maxsize=0)
        self._when_tts_done_callback_queue = Queue()

        t = Thread(target=self.worker)
        t.daemon = True
        t.start()

    # ---------------------------------------------------------
    # VOLUME SYNC
    # ---------------------------------------------------------
    def sync_volume(self, entity, attribute, old, new, kwargs):
        try:
            volume = float(self.get_state(entity, attribute="vol"))
            selected = self.get_state(self.gh_select_media_player)
            gh_player = self.check_mplayer([selected])
            self.volume_set(gh_player, volume)
        except Exception as ex:
            self.log(f"Errore sincronizzando volume Google: {ex}", level="ERROR")

    # ---------------------------------------------------------
    # MEDIA PLAYER RESOLUTION
    # ---------------------------------------------------------
    def check_mplayer(self, gh_player: list):
        gh = []
        for item in gh_player:
            if item.lower() == "tutti i google":
                members = self.get_state("group.media_player_google", attribute="entity_id")
                if members:
                    gh.extend(members)
            else:
                media_state = self.get_state("media_player")
                for entity, state in media_state.items():
                    if item == entity or item == state["attributes"].get("friendly_name"):
                        gh.append(entity)
        return gh

    def check_volume(self, gh_volume):
        media_state = self.get_state("media_player")
        gh = []
        for entity, state in media_state.items():
            friendly_name = state["attributes"].get("friendly_name")
            for item in gh_volume:
                if "gruppo" not in str(item).lower() and item == friendly_name:
                    gh.append(entity)
        return gh

    # ---------------------------------------------------------
    # VOLUME & MEDIA STATE SNAPSHOTS
    # ---------------------------------------------------------
    def volume_set(self, gh_player: list, volume: float):
        if gh_player != ["all"]:
            if volume > 1:
                volume = volume / 100.0
            for item in gh_player:
                self.call_service("media_player/volume_set", entity_id=item, volume_level=volume)

    def volume_get(self, media_player: list, volume: float):
        self.dict_volumes = {}
        for i in media_player:
            self.dict_volumes[i] = self.get_state(i, attribute="volume_level", default=volume)
        return self.dict_volumes

    def mediastate_get(self, media_player: list, volume: float):
        self.dict_info_mplayer = {}
        for i in media_player:
            self.dict_info_mplayer[i] = {}
        for i in media_player:
            self.dict_info_mplayer[i]['state'] = self.get_state(i, default='idle')
            self.dict_info_mplayer[i]['media_id'] = self.get_state(i, attribute="media_content_id", default='')
            self.dict_info_mplayer[i]['media_type'] = self.get_state(i, attribute="media_content_type", default='')
            self.dict_info_mplayer[i]['app_name'] = self.get_state(i, attribute="app_name", default='')
            self.dict_info_mplayer[i]['authSig'] = self.get_state(i, attribute="authSig", default='')
        return self.dict_info_mplayer

    # ---------------------------------------------------------
    # HELPER: ENQUEUE TTS
    # ---------------------------------------------------------
    def _enqueue_tts(self, message, volume, language, media_player, wait_time, gh_mode, gh_notifier, options):
        self.queue.put({
            "type": "tts",
            "text": message,
            "volume": volume,
            "language": language,
            "gh_player": media_player,
            "wait_time": wait_time,
            "gh_mode": gh_mode,
            "gh_notifier": gh_notifier,
            "options": options
        })

    # ---------------------------------------------------------
    # HELPER: AUDIO -> TTS
    # ---------------------------------------------------------
    def _play_audio_then_tts(
        self,
        gh_player,
        media_id,
        media_type,
        message,
        tts_volume,
        language,
        media_player,
        wait_time,
        gh_mode,
        gh_notifier,
        options
    ):
        # Volume dedicato per l'audio (se presente)
        audio_volume = tts_volume
        if options.get("audio_volume") is not None:
            try:
                audio_volume = float(options.get("audio_volume"))
            except Exception:
                pass

        self.volume_set(gh_player, audio_volume)

        # 1. Riproduci audio
        try:
            self.call_service(
                "media_extractor/play_media",
                entity_id=gh_player,
                media_content_id=media_id,
                media_content_type=media_type
            )
        except Exception as ex:
            self.log(f"Errore in media_content: {ex}", level="ERROR")

        # 2. Attendi durata audio
        try:
            time.sleep(1)  # attesa per aggiornare media_duration
            media_duration = self.get_state(gh_player[0], attribute="media_duration")

            if media_duration and float(media_duration) > 0:
                time.sleep(float(media_duration))
            else:
                time.sleep(4)
        except Exception:
            time.sleep(4)

        # 3. Delay opzionale dopo audio
        try:
            delay_after_audio = float(options.get("delay_after_audio", 0) or 0)
        except Exception:
            delay_after_audio = 0

        if delay_after_audio > 0:
            time.sleep(delay_after_audio)

        # 4. Volume dedicato per il TTS (se presente)
        if options.get("tts_volume") is not None:
            try:
                tts_volume = float(options.get("tts_volume"))
            except Exception:
                pass

        self.volume_set(gh_player, tts_volume)

        # 5. Enqueue TTS
        self._enqueue_tts(message, tts_volume, language, media_player, wait_time, gh_mode, gh_notifier, options)

    # ---------------------------------------------------------
    # HELPER: TTS -> AUDIO (usando callback when_tts_done_do)
    # ---------------------------------------------------------
    def _play_tts_then_audio(
        self,
        gh_player,
        media_id,
        media_type,
        message,
        tts_volume,
        language,
        media_player,
        wait_time,
        gh_mode,
        gh_notifier,
        options
    ):
        # Volume dedicato per il TTS (se presente)
        if options.get("tts_volume") is not None:
            try:
                tts_volume = float(options.get("tts_volume"))
            except Exception:
                pass

        self.volume_set(gh_player, tts_volume)

        # 1. Metti TTS in coda
        self._enqueue_tts(message, tts_volume, language, media_player, wait_time, gh_mode, gh_notifier, options)

        # 2. Definisci callback per riprodurre l'audio dopo il TTS
        def _audio_callback():
            audio_volume = tts_volume
            if options.get("audio_volume") is not None:
                try:
                    audio_volume = float(options.get("audio_volume"))
                except Exception:
                    pass

            self.volume_set(gh_player, audio_volume)

            try:
                self.call_service(
                    "media_extractor/play_media",
                    entity_id=gh_player,
                    media_content_id=media_id,
                    media_content_type=media_type
                )
            except Exception as ex:
                self.log(f"Errore in media_content (callback): {ex}", level="ERROR")

        self.when_tts_done_do(_audio_callback)

    # ---------------------------------------------------------
    # SPEAK (VERSIONE ESTESA, SOFT MODE)
    # ---------------------------------------------------------
    def speak(self, google, gh_mode: bool, gh_notifier: str):

        google = h.normalize_google_payload(
            google=google,
            default_player=self.gh_select_media_player,
            default_volume=0.5,
            tts_period_volume=self.get_state(self.tts_period_of_day_volume, attribute="vol")
            if self.tts_period_of_day_volume else None
        )

        message = google["message"]
        volume = google["volume"]
        language = google["language"]
        media_player = google["media_player"]
        media_id = google["media_content_id"]
        media_type = google["media_content_type"]
        options = google.get("options", {}) or {}

        # Volumi separati (di base uguali)
        tts_volume = float(volume)
        if options.get("tts_volume") is not None:
            try:
                tts_volume = float(options.get("tts_volume"))
            except Exception:
                pass

        # Se only_tts è true, ignoriamo completamente l'audio
        if options.get("only_tts", False):
            media_id = ""

        gh_player = self.check_mplayer(media_player)
        gh_volume = self.check_volume(
            self.get_state(self.gh_select_media_player, attribute="options")
        )

        self.volume_get(
            gh_volume,
            float(self.get_state(self.args["gh_restore_volume"])) / 100
        )
        self.mediastate_get(
            gh_volume,
            float(self.get_state(self.args["gh_restore_volume"])) / 100
        )

        wait_time = float(self.get_state(self.gh_wait_time))

        # Volume iniziale (manteniamo il comportamento attuale come base)
        self.volume_set(gh_player, volume)

        # Aggiorna centro notifiche
        try:
            self.set_state(
                "sensor.centro_notifiche",
                state="ready",
                attributes={
                    "friendly_name": "Centro Notifiche",
                    "detail": f"Messaggio inviato a {gh_player} (Google)",
                    "volume": volume,
                    "message": message,
                    "notifier": gh_notifier,
                    "mode": gh_mode,
                    "last_message": message,
                    "last_target": gh_player,
                    "last_volume": volume,
                    "last_update": datetime.now().strftime("%d.%m.%Y - %H:%M:%S")
                }
            )
        except Exception as ex:
            self.log(f"Errore aggiornando centro_notifiche (Google): {ex}", level="ERROR")

        # -----------------------------------------------------
        # CASO: ONLY AUDIO
        # -----------------------------------------------------
        if media_id and options.get("only_audio", False):
            audio_volume = volume
            if options.get("audio_volume") is not None:
                try:
                    audio_volume = float(options.get("audio_volume"))
                except Exception:
                    pass

            self.volume_set(gh_player, audio_volume)

            try:
                self.call_service(
                    "media_extractor/play_media",
                    entity_id=gh_player,
                    media_content_id=media_id,
                    media_content_type=media_type
                )
            except Exception as ex:
                self.log(f"Errore in media_content (only_audio): {ex}", level="ERROR")

            return

        # -----------------------------------------------------
        # CASO: AUDIO PRESENTE E NON only_tts
        # audio_first True  -> Audio -> TTS (come ora, ma esteso)
        # audio_first False -> TTS  -> Audio (via callback)
        # -----------------------------------------------------
        if media_id and not options.get("only_tts", False):
            audio_first = options.get("audio_first", True)

            if audio_first:
                # AUDIO -> TTS (sequenza estesa)
                self._play_audio_then_tts(
                    gh_player=gh_player,
                    media_id=media_id,
                    media_type=media_type,
                    message=message,
                    tts_volume=tts_volume,
                    language=language,
                    media_player=media_player,
                    wait_time=wait_time,
                    gh_mode=gh_mode,
                    gh_notifier=gh_notifier,
                    options=options
                )
                return
            else:
                # TTS -> AUDIO (via callback)
                self._play_tts_then_audio(
                    gh_player=gh_player,
                    media_id=media_id,
                    media_type=media_type,
                    message=message,
                    tts_volume=tts_volume,
                    language=language,
                    media_player=media_player,
                    wait_time=wait_time,
                    gh_mode=gh_mode,
                    gh_notifier=gh_notifier,
                    options=options
                )
                return

        # -----------------------------------------------------
        # CASO STANDARD / ONLY TTS / NESSUN AUDIO
        # -----------------------------------------------------
        self._enqueue_tts(message, tts_volume, language, media_player, wait_time, gh_mode, gh_notifier, options)

    # ---------------------------------------------------------
    # WHEN TTS DONE CALLBACK
    # ---------------------------------------------------------
    def when_tts_done_do(self, callback: callable) -> None:
        self._when_tts_done_callback_queue.put(callback)

    # ---------------------------------------------------------
    # WORKER (VERSIONE ORIGINALE, ESTESO CON OPTIONS)
    # ---------------------------------------------------------
    def worker(self):
        # Il worker è esteso solo per gestire options (interrupt/resume)
        while True:
            opts = {}
            try:
                data = self.queue.get()
                opts = data.get("options", {}) if isinstance(data, dict) else {}
                duration = 0
                gh_player = self.check_mplayer(h.safe_list(data["gh_player"]))

                if data["gh_mode"].lower() == 'google assistant':
                    self.call_service(__NOTIFY__ + data["gh_notifier"], message=data["text"])
                else:
                    entity = gh_player[0] if len(gh_player) == 1 else gh_player

                    # Gestione interrupt ytube (rispettando options.interrupt)
                    if opts.get("interrupt", True):
                        if self.get_state(self.ytube_player) == "playing" and self.get_state(entity) == "playing":
                            self.call_service("ytube_music_player/call_method", entity_id=self.ytube_player, command="interrupt_start")
                            self.ytube_called = True
                            time.sleep(1)

                    message_clean = h.replace_regular(data["text"], SUB_VOICE)
                    words = len(h.remove_tags(message_clean).split())
                    chars = len(h.remove_tags(message_clean))
                    duration = (words * 0.007) * 60
                    if h.has_numbers(message_clean):
                        duration = 4
                    if words > 0 and (chars / words) > 7 and chars > 90:
                        duration = 7

                    service_name = data["gh_notifier"]

                    # Se è un servizio TTS nativo → prefisso tts/
                    if service_name.startswith("google_") or service_name.startswith("cloud_") or service_name.startswith("google_translate"):
                        full_service = "tts/" + service_name

                    # Se è Reverso → usa il servizio custom
                    elif service_name == "reversotts.say":
                        full_service = "reversotts/say"

                    # Altri servizi (es. google_assistant_sdk)
                    else:
                        full_service = service_name

                    self.call_service(full_service, entity_id=entity, message=data["text"])

                    media_duration = self.get_state(entity, attribute='media_duration')
                    if not media_duration or float(media_duration) > 60 or float(media_duration) == -1:
                        duration += data["wait_time"]
                    else:
                        duration = float(media_duration) + data["wait_time"]

                    time.sleep(duration)

                    if self.ytube_called:
                        self.call_service("media_player/volume_set", entity_id=entity, volume_level=0)

            except Exception as ex:
                self.log(f"Errore nel Worker: {ex}", level="ERROR")
                self.log(sys.exc_info())

            self.queue.task_done()

            if self.queue.qsize() == 0:
                if hasattr(self, "dict_volumes"):
                    for i, j in self.dict_volumes.items():
                        self.call_service("media_player/volume_set", entity_id=i, volume_level=j)
                        self.set_state(i, state="", attributes={"volume_level": j})

                if hasattr(self, "dict_info_mplayer"):
                    for k, v in self.dict_info_mplayer.items():
                        temp_media_id = v.get("media_id", "")
                        temp_media_type = v.get("media_type", "")
                        temp_app_name = v.get("app_name", "")
                        temp_auth_sig = v.get("authSig", "")
                        playing = (v.get("state") == "playing")

                        # Ripresa ytube rispettando options.resume
                        if self.ytube_called and opts.get("resume", True):
                            self.call_service("ytube_music_player/call_method", entity_id=self.ytube_player, command="interrupt_resume")

                        if playing and temp_auth_sig != "":
                            self.call_service("media_player/play_media", entity_id=k,
                                              media_content_id=temp_media_id,
                                              media_content_type=temp_media_type,
                                              authSig=temp_auth_sig)
                        elif playing and temp_app_name == 'Spotify':
                            self.call_service("spotcast/start", entity_id=k, force_playback=True)
                        elif playing:
                            self.call_service("media_player/play_media", entity_id=k,
                                              media_content_id=temp_media_id,
                                              media_content_type=temp_media_type)

                try:
                    while self._when_tts_done_callback_queue.qsize() > 0:
                        callback_func = self._when_tts_done_callback_queue.get_nowait()
                        callback_func()
                        self._when_tts_done_callback_queue.task_done()
                except Exception:
                    pass