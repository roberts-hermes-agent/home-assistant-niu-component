from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import time
import hashlib
import json

# from homeassistant.util import Throttle
from time import gmtime, strftime

import requests

from .const import *


class NiuApi:
    def __init__(self, username, password, scooter_id) -> None:
        self.username = username
        self.password = password
        self.scooter_id = int(scooter_id)

        self.dataBat = None
        self.dataMoto = None
        self.dataMotoInfo = None
        self.dataTrackInfo = None
        self.dataRideStat = None
        self.dataTrackSummary = None
        self.dataMedicalRecord = None
        self.dataKeyShareStats = None
        self._track_summary_updated_at = 0
        self.is_kqi = False

    def initApi(self):
        self.token = self.get_token()
        api_uri = MOTOINFO_LIST_API_URI
        vehicle = self.get_vehicles_info(api_uri)["data"]["items"][self.scooter_id]
        self.sn = vehicle["sn_id"]
        self.sensor_prefix = vehicle["scooter_name"]
        self.product_type = vehicle.get("product_type", "")
        self.is_kqi = self.product_type.startswith("ble_kick_scooter") or self.product_type.startswith("kick_scooter")
        self.updateBat()
        self.updateMoto()
        self.updateMotoInfo()
        self.updateTrackInfo()

    def get_token(self):
        username = self.username
        password = self.password

        url = ACCOUNT_BASE_URL + LOGIN_URI
        md5 = hashlib.md5(password.encode("utf-8")).hexdigest()
        data = {
            "account": username,
            "password": md5,
            "grant_type": "password",
            "scope": "base",
            "app_id": "niu_ktdrr960",
        }
        try:
            r = requests.post(url, data=data)
        except BaseException as e:
            print(e)
            return False
        data = json.loads(r.content.decode())
        return data["data"]["token"]["access_token"]

    def get_vehicles_info(self, path):
        token = self.token

        url = API_BASE_URL + path
        headers = {"token": token}
        try:
            r = requests.get(url, headers=headers, data=[])
        except ConnectionError:
            return False
        if r.status_code != 200:
            return False
        data = json.loads(r.content.decode())
        return data

    def get_info(
        self,
        path,
    ):
        sn = self.sn
        token = self.token
        url = API_BASE_URL + path

        params = {"sn": sn}
        headers = {
            "token": token,
            "user-agent": "manager/4.10.4 (android; IN2020 11);lang=zh-CN;clientIdentifier=Domestic;timezone=Asia/Shanghai;model=IN2020;deviceName=IN2020;ostype=android",
        }
        try:
            r = requests.get(url, headers=headers, params=params)

        except ConnectionError:
            return False
        if r.status_code != 200:
            return False
        data = json.loads(r.content.decode())
        if data["status"] != 0:
            return False
        return data

    def post_info(
        self,
        path,
    ):
        sn, token = self.sn, self.token
        url = API_BASE_URL + path
        params = {}
        headers = {"token": token, "Accept-Language": "en-US"}
        try:
            r = requests.post(url, headers=headers, params=params, data={"sn": sn})
        except ConnectionError:
            return False
        if r.status_code != 200:
            return False
        data = json.loads(r.content.decode())
        if data["status"] != 0:
            return False
        return data

    def post_info_track(self, path):
        if self.is_kqi:
            return self.get_kqi_track_list(index=0, page_size=10)

        sn, token = self.sn, self.token
        url = API_BASE_URL + path
        params = {}
        headers = {
            "token": token,
            "Accept-Language": "en-US",
            "User-Agent": "manager/1.0.0 (identifier);clientIdentifier=identifier",
        }
        try:
            r = requests.post(
                url,
                headers=headers,
                params=params,
                json={"index": "0", "pagesize": 10, "sn": sn},
            )
        except ConnectionError:
            return False
        if r.status_code != 200:
            return False
        data = json.loads(r.content.decode())
        if data["status"] != 0:
            return False
        return data

    def get_kqi_track_list(self, index=0, page_size=10):
        sn, token = self.sn, self.token
        url = API_BASE_URL + KQI_TRACK_LIST_API_URI
        headers = {
            "token": token,
            "Accept-Language": "de-DE",
            "User-Agent": "manager/5.12.2 (android; IN2020 11);lang=de-DE;clientIdentifier=Overseas;timezone=Europe/Berlin;model=IN2020;deviceName=IN2020;ostype=android",
        }
        try:
            r = requests.get(url, headers=headers, params={"sn": sn, "index": index, "pageSize": page_size})
        except ConnectionError:
            return False
        if r.status_code != 200:
            return False
        data = json.loads(r.content.decode())
        if data["status"] != 0:
            return False
        return data

    def get_kqi_ride_stat(self):
        sn, token = self.sn, self.token
        url = API_BASE_URL + KQI_RIDE_STAT_API_URI
        headers = {"token": token, "Accept-Language": "de-DE"}
        try:
            r = requests.get(url, headers=headers, params={"sn": sn})
        except ConnectionError:
            return False
        if r.status_code != 200:
            return False
        data = json.loads(r.content.decode())
        if data["status"] != 0:
            return False
        return data

    def get_kqi_medical_record(self):
        return self.get_info(KQI_MEDICAL_RECORD_API_URI)

    def get_kqi_key_share_statistics(self):
        return self.get_info(KQI_KEY_SHARE_STATISTICS_API_URI)

    def _latest_track(self):
        if not self.dataTrackInfo:
            return {}
        data = self.dataTrackInfo.get("data", {})
        if isinstance(data, dict):
            items = data.get("items", [])
        elif isinstance(data, list):
            items = data
        else:
            items = []
        return items[0] if items else {}

    def getDataBat(self, id_field): 
        return self.dataBat["data"]["batteries"]["compartmentA"][id_field]

    def getDataMoto(self, id_field):
        return self.dataMoto["data"][id_field]

    def getDataDist(self, id_field):
        last_track = self.dataMoto["data"].get("lastTrack") or {}
        if id_field in last_track:
            return last_track[id_field]
        if self.dataTrackInfo is None:
            self.updateTrackInfo()
        track = self._latest_track()
        if id_field == "ridingTime":
            return track.get("ridingtime", track.get("ridingTime", 0))
        return track.get(id_field, 0)

    def getDataPos(self, id_field):
        return self.dataMoto["data"]["postion"][id_field]

    def getDataOverall(self, id_field):
        return self.dataMotoInfo["data"][id_field]

    def getDataTrack(self, id_field):
        track = self._latest_track()
        if id_field == "startTime" or id_field == "endTime":
            value = track.get(id_field, 0)
            if not value:
                return 0
            try:
                tz = ZoneInfo("Europe/Berlin")
            except Exception:
                tz = None
            return datetime.fromtimestamp(value / 1000, tz=tz).strftime("%Y-%m-%d %H:%M:%S")
        if id_field == "ridingtime":
            return strftime("%H:%M:%S", gmtime(track.get(id_field, 0)))
        if id_field == "track_thumb":
            thumburl = track.get(id_field, "") or ""
            if "app-api.niucache.com" in thumburl:
                thumburl = thumburl.replace("app-api.niucache.com", "app-api-fk.niu.com")
            return thumburl.replace("/track/thumb/", "/track/overseas/thumb/")
        return track.get(id_field, 0)

    def getDataRideStat(self, id_field):
        if not self.dataRideStat:
            return 0
        return self.dataRideStat.get("data", {}).get(id_field, 0)

    def get_kqi_track_summary(self):
        if not self.is_kqi:
            return {"ride_count_total": 0, "riding_minutes_total": 0, "sharing_savings_total": 0}

        page_size = 100
        # NIU's KQi endpoint treats index=0 and index=1 as the first page;
        # subsequent pages start at index=2.
        index = 0
        rides = []
        seen_track_ids = set()

        while index < 100:
            data = self.get_kqi_track_list(index=index, page_size=page_size)
            if not data:
                break
            payload = data.get("data", {})
            items = payload.get("items", []) if isinstance(payload, dict) else []
            if not items:
                break

            new_items = 0
            for item in items:
                track_id = item.get("trackId") or f"{item.get('startTime')}-{item.get('endTime')}-{item.get('distance')}"
                if track_id in seen_track_ids:
                    continue
                seen_track_ids.add(track_id)
                new_items += 1
                rides.append(item)

            if new_items == 0 or len(items) < page_size:
                break
            index = 2 if index == 0 else index + 1

        tz = ZoneInfo("Europe/Berlin")
        now = datetime.now(tz)
        month_rides = []
        ride_count = len(rides)
        distance_total = 0.0
        riding_seconds = 0.0
        power_total = 0.0
        longest_distance = 0.0
        longest_duration = 0.0
        last_ride_power = 0.0

        for pos, item in enumerate(rides):
            try:
                distance = float(item.get("distance") or 0)
            except (TypeError, ValueError):
                distance = 0.0
            try:
                duration = float(item.get("ridingTime") or item.get("riding_time") or item.get("ridingtime") or 0)
            except (TypeError, ValueError):
                duration = 0.0
            try:
                power = float(item.get("power_consumption") or 0)
            except (TypeError, ValueError):
                power = 0.0

            distance_total += distance
            riding_seconds += duration
            power_total += power
            longest_distance = max(longest_distance, distance)
            longest_duration = max(longest_duration, duration)
            if pos == 0:
                last_ride_power = power

            try:
                start = datetime.fromtimestamp(float(item.get("startTime") or 0) / 1000, tz=tz)
            except (TypeError, ValueError, OSError):
                start = None
            if start and start.year == now.year and start.month == now.month:
                month_rides.append((distance, duration, power))

        riding_minutes = round(riding_seconds / 60, 2)
        distance_total_km = round(distance_total / 1000, 2)
        sharing_cost = round((ride_count * 0.49) + (riding_minutes * 0.36), 2)
        sharing_savings = round(sharing_cost - 599, 2)
        amortization_percent = round((sharing_cost / 599) * 100, 1) if sharing_cost else 0

        month_count = len(month_rides)
        month_distance_km = round(sum(x[0] for x in month_rides) / 1000, 2)
        month_minutes = round(sum(x[1] for x in month_rides) / 60, 2)
        month_sharing_cost = round((month_count * 0.49) + (month_minutes * 0.36), 2)

        return {
            "ride_count_total": ride_count,
            "riding_minutes_total": riding_minutes,
            "sharing_cost_total": sharing_cost,
            "sharing_savings_total": sharing_savings,
            "amortization_percent": amortization_percent,
            "distance_total_from_tracks": distance_total_km,
            "ride_count_this_month": month_count,
            "riding_minutes_this_month": month_minutes,
            "distance_this_month": month_distance_km,
            "sharing_cost_this_month": month_sharing_cost,
            "longest_ride_distance": round(longest_distance / 1000, 2),
            "longest_ride_duration": round(longest_duration / 60, 2),
            "average_ride_distance": round((distance_total / ride_count) / 1000, 2) if ride_count else 0,
            "average_ride_duration": round((riding_seconds / ride_count) / 60, 2) if ride_count else 0,
            "power_consumption_total": round(power_total, 2),
            "last_ride_power_consumption": last_ride_power,
        }

    def getDataTrackSummary(self, id_field):
        if not self.dataTrackSummary:
            return 0
        return self.dataTrackSummary.get(id_field, 0)

    def getDataMedicalRecord(self, id_field):
        if not self.dataMedicalRecord:
            return 0
        return self.dataMedicalRecord.get("data", {}).get(id_field, 0)

    def getDataKeyShareStats(self, id_field):
        if not self.dataKeyShareStats:
            return 0
        return self.dataKeyShareStats.get("data", {}).get(id_field, 0)

    def updateBat(self):
        self.dataBat = self.get_info(MOTOR_BATTERY_API_URI)

    def updateMoto(self):
        self.dataMoto = self.get_info(MOTOR_INDEX_API_URI)

    def updateMotoInfo(self):
        self.dataMotoInfo = self.post_info(MOTOINFO_ALL_API_URI)

    def updateTrackInfo(self):
        self.dataTrackInfo = self.post_info_track(TRACK_LIST_API_URI)

    def updateRideStat(self):
        self.dataRideStat = self.get_kqi_ride_stat()

    def updateTrackSummary(self):
        # Several sensors are backed by the same paginated ride-list scan; cache
        # the result briefly so one HA update cycle does not hammer NIU login/API.
        if self.dataTrackSummary and (time.time() - self._track_summary_updated_at) < 600:
            return
        self.dataTrackSummary = self.get_kqi_track_summary()
        self._track_summary_updated_at = time.time()

    def updateMedicalRecord(self):
        self.dataMedicalRecord = self.get_kqi_medical_record()

    def updateKeyShareStats(self):
        self.dataKeyShareStats = self.get_kqi_key_share_statistics()


"""class NiuDataBridge(object):
    async def __init__(self, api):
    #  hass, username, password, country, scooter_id):

        self.api = api
        # await hass.async_add_executor_job(lambda : NiuDataBridge(username, password, country, scooter_id))
        # NiuApi(username, password, country, scooter_id)
        sn, token = self.api.sn, self.api.token

        self._dataBat = None
        self._dataMoto = None
        self._dataMotoInfo = None
        self._dataTrackInfo = None
        self._sn = sn
        self._token = token

    def token(self):
        return self.api.token
    
    def sn(self):
        return self.api.sn

    def sensor_prefix(self):
        return self.api.sensor_prefix

    def dataBat(self, id_field):
        return self._dataBat["data"]["batteries"]["compartmentA"][id_field]

    def dataMoto(self, id_field):
        return self._dataMoto["data"][id_field]

    def dataDist(self, id_field):
        return self._dataMoto["data"]["lastTrack"][id_field]

    def dataPos(self, id_field):
        return self._dataMoto["data"]["postion"][id_field]

    def dataOverall(self, id_field):
        return self._dataMotoInfo["data"][id_field]

    def dataTrack(self, id_field):
        if id_field == "startTime" or id_field == "endTime":
            return datetime.fromtimestamp(
                (self._dataTrackInfo["data"][0][id_field]) / 1000
            ).strftime("%Y-%m-%d %H:%M:%S")
        if id_field == "ridingtime":
            return strftime(
                "%H:%M:%S", gmtime(self._dataTrackInfo["data"][0][id_field])
            )
        if id_field == "track_thumb":
            thumburl = self._dataTrackInfo["data"][0][id_field].replace(
                "app-api.niucache.com", "app-api-fk.niu.com"
            )
            return thumburl.replace("/track/thumb/", "/track/overseas/thumb/")
        return self._dataTrackInfo["data"][0][id_field]

    @Throttle(timedelta(seconds=1))
    def updateBat(self):
        self._dataBat = self.api.get_info(MOTOR_BATTERY_API_URI)

    @Throttle(timedelta(seconds=1))
    def updateMoto(self):
        self._dataMoto = self.api.get_info(MOTOR_INDEX_API_URI)

    @Throttle(timedelta(seconds=1))
    def updateMotoInfo(self):
        self._dataMotoInfo = self.api.post_info(MOTOINFO_ALL_API_URI)

    @Throttle(timedelta(seconds=1))
    def updateTrackInfo(self):
        self._dataTrackInfo = self.api.post_info_track(TRACK_LIST_API_URI)"""
