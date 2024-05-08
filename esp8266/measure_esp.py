import gc
from time import sleep, time

import uasyncio as asyncio
import urequests
from dht import DHT22
from ds18x20 import DS18X20

class glog:
    def __init__(self, wlan, config):
        self.wlan = wlan
        self.queue = []
        self.config = config

    def _housekeeping(self):
        if len(self.queue) > config["HISTORY_MAX_LEN"]:
            del self.queue[0 : config["HISTORY_MAX_LEN"]]  # noqa E203

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
        if todisk and config["LOG_TO_DISK"]:
            with open(config["LOG_FILE"], "w") as fh:
                fh.write(f"{now} {x}")
        if wlan.isconnected():
            post_data = ujsondumps({"th": f"{x}", "time": f"{now}", "l": "log"})
            urequests.post(config["LOG_URL"], data=post_data)
            if self.queue:
                for _qmessage in self.queue:
                    qmessage = f"QUEUED {_qmessage}"
                    print(f"sending {qmessage}")
                    post_data = ujsondumps(
                        {"th": qmessage, "time": f"{now}", "l": "log"}
                    )
                    urequests.post(config["LOG_URL"], data=post_data)
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


async def do_measure(sensor):
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


async def handle_tosend(history):
    for name in list(sensors.keys()):
        for k, v in history["tosend"][name].items():
            res = await send_message(location=name, th=k, now=v)
            if not res:
                print(f"cannot send message {name} {k} {v}")
                return
            history["tosend"][name].pop(k)


async def send_message(th, now, location):
    log.glog(f"send_message {location} {now} {th}", localonly=True)
    try:
        url = config["SEND_URL"].format(location=location, th=th, now=now)
        urequests.get(url)
        return True
    except Exception as ex:
        log.glog(f"send_message failure: {ex}", todisk=True)
        return False


async def main(history, sensors, wlan):
    t0 = t_network = t_ntp = int(time())
    ntp_init = False
    # _ = asyncio.create_task(do_connect(wlan))
    await do_connect(wlan)
    await asyncio.sleep(0.1)
    if wlan.isconnected():
        try:
            await settime()
            ntp_init = True
        except Exception as ex:
            log.glog(f"166cannot set time: {ex}", todisk=True)
    while True:
        now = int(time())
        mem_free = gc.mem_free()
        if mem_free < 10000:
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

        if not now % config["SAMPLING_TIME"]:
            for name, sensor in sensors.items():
                th = False
                if not sensor.get("enabled"):
                    continue
                try:
                    th = await do_measure(sensor)
                except Exception as ex:
                    log.glog(f"194cannot get temp on {name}: {ex}", todisk=True)
                if th:
                    if await send_message(th, now, location=name):
                        await handle_tosend(history)
                    else:
                        clean_old_history()
                        # this could be a list, TODO?
                        history["tosend"][name][now] = th
                        log.glog(f"history is now: {history}")
        if not now % config["GC_TIME"]:
            gc.collect()
        sleep(1)


wlan = WLAN(STA_IF)
wlan.active(True)
wlan.disconnect()
history = init_history()
gc.enable()
log = glog(wlan, config)
log.glog("Starting")

asyncio.run(main(history, sensors, wlan))
