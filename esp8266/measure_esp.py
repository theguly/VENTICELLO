import gc
from time import sleep, time

import machine
import uasyncio as asyncio
import urequests
from config import config, relais, sensors
from network import STA_IF, WLAN
from ntptime import settime
from ujson import dumps as ujsondumps
from ujson import loads as ujsonloads
from uos import rename, stat


class glog:
    def __init__(self, wlan, config):
        self.wlan = wlan
        self.queue = []
        self.config = config

    @staticmethod
    def _urlencode(string):

        encoded_string = ""

        for character in string:
            if character.isalpha() or character.isdigit():
                encoded_string += character
            else:
                encoded_string += f"%{ord(character):x}"

        return encoded_string

    def _housekeeping(self):
        if len(self.queue) > config["HISTORY_MAX_LEN"]:
            del self.queue[0 : config["HISTORY_MAX_LEN"]]  # noqa E203

        # untested
        if config.get("LOG_TO_DISK") and config.get("LOG_FILE"):
            try:
                offset = stat(config["LOG_FILE"])[6] - config["LOG_FILE_MAX_SIZE"]
            except:
                return
            if offset:
                rename(config["LOG_FILE"], "/log.old")
                fh_i = open("/log.old", "r")
                fh_o = open(config["LOG_FILE"], "w")
                fh_i.seek(-offset, 2)

                fh_o.write((fh_i.read()))
                fh_o.close()
                fh_i.close()

    def _telegram(self, msg):
        if not self.config.get("TELEGRAM_API_TOKEN") or not self.config.get("TELEGRAM_CHANNEL"):
            return
        msg = self._encode(msg)
        urequests.post(
            f'https://api.telegram.org/bot{config["TELEGRAM_API_TOKEN"]}/sendMessage?chat_id={config["TELEGRAM_CHANNEL"]}&text={msg}'
        )

    def glog(self, x=None, todisk=False, localonly=False, **kwargs):
        self._housekeeping()

        now = int(time())
        x = f"{x if x else ''}"
        if kwargs:
            for k, v in kwargs.items():
                x = f"{x} - {k}:{v}"
        if localonly:
            x = f"{x} L"
        print(f"{now} {x}")
        if localonly:
            return
        if config["LOG_TO_DISK"] and todisk:
            with open(config["LOG_FILE"], "w") as fh:
                fh.write(f"{now} {x}")

        if wlan.isconnected():
            self._telegram({x})
            post_data = ujsondumps({"th": f"{x}", "time": f"{now}", "l": "log"})
            urequests.post(config["BASE_URL"], data=post_data)
            if self.queue:
                for _qmessage in self.queue:
                    qmessage = f"QUEUED {_qmessage}"
                    print(f"sending {qmessage}")
                    post_data = ujsondumps({"th": qmessage, "time": f"{now}", "l": "log"})
                    urequests.post(config["BASE_URL"], data=post_data)
                    self._telegram({qmessage})

                    # no mercy
                    try:
                        self.queue.remove(_qmessage)
                    except:
                        print(f"cannot remove {_qmessage}")
                print(self.queue)
        else:
            print(f"queued {now} {x}")
            self.queue.append(f"{now} {x}")


def init_history():
    history = {"sent": {}, "tosend": {}}
    for sensor in sensors.keys():
        history["tosend"][sensor] = {}
    return history


def init_relais():
    relais = config.get("relais", {})
    for relay in relais.values():
        if not relay.get("enabled", True):
            continue
        for loc_pin in relay.get("loc", {}).values():
            loc_pin.value(1)  # off
        relay["control"] = False
        if not relay.get("delta"):
            relay["delta"] = 1


def init_sensors():
    sensors = config.get("sensors", {})
    for sensor in sensors.values():
        sensor["last_measure"] = 0
        sensor["missed_measure"] = 0


def trigger_relay(relay, action, value):
    target = relay["loc"].get(action)
    if not target:
        log.glog(f"...no relay available for {action}?!")
        return False
    z = getattr(target, value)
    z()
    return True


def clean_old_history():
    for sensor in sensors.keys():
        if len(history["tosend"][sensor]) > config["HISTORY_MAX_LEN"]:
            k = list(history["tosend"][sensor].keys())
            k = k.sort()
            for d in k[0 : config["HISTORY_MAX_LEN"]]:  # noqa E302
                del history["tosend"][sensor][d]


async def do_connect(wlan):
    if not wlan.isconnected():
        log.glog(f"Connecting to network {config['WIFI_SSID']}")
        wlan.connect(config["WIFI_SSID"], config["WIFI_PASSWORD"])
    log.glog(do_connect=f"Connected: {wlan.isconnected()}")


async def do_measure(prev_measure_time):
    for name, sensor in sensors.items():
        if not sensor.get("enabled"):
            continue
        if (sensor.get("last_measure", 0) > prev_measure_time) and not relais.get(sensor, {}).get("control"):
            continue

        try:
            th = await get_temp(sensor)
        except Exception as ex:
            th = False
            log.glog(f"161cannot get temp on {name}: {ex}", todisk=True)

        if th:
            now = int(time())
            sensor["missed_measure"] = 0
            sensor["last_measure"] = now
            await check_control_temperature(sensor, th, now)
            if await send_measure(th, now, location=name):
                await handle_tosend()
            else:
                clean_old_history()
                # this could be a list, TODO?
                history["tosend"][name][now] = th
                log.glog(f"history is now: {history}")
        else:
            if sensor not in relais:
                continue
            sensor["missed_measure"] += 1
            if sensor["missed_measure"] >= 3:
                # shutdown all the relays
                trigger_relay(relais[sensor], "heating", "off")
                trigger_relay(relais[sensor], "cooling", "off")
                sensor["missed_measure"] = 0
                log.glog(f"shutting down all relais for sensor {sensor}")
    return


async def check_control_temperature(sensor, th, now):
    if not relais:
        return
    if sensor not in relais:
        return
    relay = relais[sensor]
    if not relay.get("enabled"):
        return

    if relay["control"]:
        # we want the temp to be our target
        if now < (sensor.get("last_measure") + config.get("TEMP_CONTROL_RECHECK", 60)):
            return

        if th > relay["target_temp"]:
            log.glog(f'Temp for sensor {sensor} is still above the limit: {th} > {relay["target_temp"]} COOLING')
            return
            # return trigger_relay(relay, "cooling", "on")
        if th < relay["target_temp"] - relay["delta"]:
            log.glog(f'Temp for sensor {sensor} is still below the limit: {th} < {relay["target_temp"]} HEATING')
            return
            # return trigger_relay(relay, "heating", "on")

        log.glog(f'Temp for sensor {sensor} ok: {th}~={relay["target_temp"]} relay off')
        trigger_relay(relay, "cooling", "off")
        trigger_relay(relay, "heating", "off")
        relay["control"] = False
        relay["misses_measure"] = 0

        return

    # otherwise, apply delta temp to prevent frequent up/down
    if th > relay["target_temp"] + relay["delta"]:
        log.glog(f'Temp for sensor {sensor} is above the limit: {th} > {relay["target_temp"] + relay["delta"]} COOLING')
        trigger_relay(relay, "cooling", "on")
        relay["control"] = True
        return

    if th < relay["target_temp"] - relay["delta"]:
        log.glog(f'Temp for sensor {sensor} is below the limit: {th} < {relay["target_temp"] - relay["delta"]} HEATING')
        trigger_relay(relay, "heating", "on")
        relay["control"] = True
        return

    return


async def get_temp(sensor):
    term = sensor["loc"]
    if sensor["type"] == "dht":
        term.measure()
        th = term.temperature()
        if th:
            return th
        return None
    if sensor["type"] == "ds":
        try:
            term.convert_temp()
        except Exception as e:
            log.glog(f"convert_temp exception: {e}")
            # should i break here?
        sleep(0.1)
        try:
            th = term.read_temp(sensor["rom"])
        except Exception as e:
            log.glog(f"read_temp exception: {e}")
            return None
        if th:
            return th
        return None
    log.glog(f"unknown sensor type {sensor['type']}")
    return None


async def handle_tosend():
    for name in list(sensors.keys()):
        for k, v in history["tosend"][name].items():
            res = await send_measure(location=name, th=k, now=v)
            if not res:
                print(f"cannot send message {name} {k} {v}")
                return
            history["tosend"][name].pop(k)


async def send_measure(th, now, location):
    log.glog(f"send_measure {location} {now} {th}", localonly=True)
    try:
        url = config["BASE_URL"] + f"?th={th}&time={now}&l={location}"
        urequests.get(url)
        return True
    except Exception as ex:
        log.glog(f"send_measure failure: {ex}", todisk=True)
        return False


async def main(wlan):
    t0 = t_network = t_ntp = t_measure = int(time())
    ntp_init = False
    await do_connect(wlan)
    await asyncio.sleep(0.1)
    if wlan.isconnected():
        try:
            settime()
            ntp_init = True
        except Exception as ex:
            log.glog(f"160cannot set time: {ex}", todisk=True)

    while True:
        now = int(time())
        if gc.mem_free() < 10000:
            gc.collect()
        print(f"just to say: {now} - mem_free: {gc.mem_free()}")
        if not wlan.isconnected():
            if (now - t_network) > (config["WIFI_CONNECT_TIME"]) or t0 == t_network:
                t_network = now
                await do_connect(wlan)
                asyncio.sleep(0.1)
        else:
            if (now - t_ntp) > config["NTP_SYNC_TIME"] or not ntp_init:
                try:
                    settime()
                    ntp_init = int(time())
                    t_ntp = int(time())
                except Exception as ex:
                    log.glog(f"184cannot set time: {ex}")

        t_delta = now - config["SAMPLING_TIME"]
        if (any(x.get("last_measure", 0) <= t_delta for x in sensors.values())) or (
            any(x.get("control") for x in relais.values())
        ):
            await do_measure(t_delta)

        if not now % config["GC_TIME"]:
            gc.collect()
        sleep(1)


wlan = WLAN(STA_IF)
wlan.active(True)
wlan.disconnect()
history = init_history()
init_relais()
init_sensors()
gc.enable()
log = glog(wlan, config)
log.glog("Starting")

asyncio.run(main(wlan))
