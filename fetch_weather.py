#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
江津天气抓取脚本 —— 数据源：中国天气网（中国气象局官方 weather.com.cn）
抓取 d1.weather.com.cn/weather_index/101040500.html (江津区)
GBK 解码 -> 解析实况 / AQI / 生活指数 / 5日预报 -> 输出 weather.json
用法: python fetch_weather.py [输出路径]
"""
import json, re, sys, os, time, datetime
import urllib.request

CITY_ID = "101040500"   # 重庆江津
CITY_NAME = "重庆市江津区"
URL = "http://d1.weather.com.cn/weather_index/" + CITY_ID + ".html"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "weather.json")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
    "Referer": "http://www.weather.com.cn/",
    "Accept": "*/*",
}

# 天气码 -> 专业中文表述 (中国天气网 fa/fb 码)
WCODE = {
    "00": "晴", "01": "晴间多云", "02": "多云", "03": "阴",
    "04": "阵雨", "05": "雷阵雨", "06": "雷阵雨伴冰雹", "07": "小雨",
    "08": "中雨", "09": "大雨", "10": "暴雨", "11": "大暴雨", "12": "特大暴雨",
    "13": "冻雨", "14": "阵雪", "15": "小雪", "16": "中雪", "17": "大雪",
    "18": "暴雪", "19": "雨夹雪", "20": "小雨转中雨", "21": "中雨转大雨",
    "22": "大雨转暴雨", "23": "暴雨转大暴雨", "24": "大暴雨转特大暴雨",
    "25": "雨夹雪转中雪", "26": "中雪转大雪", "27": "大雪转暴雪", "28": "雾",
    "29": "浮尘", "30": "扬沙", "31": "沙尘暴", "32": "强沙尘暴", "33": "霾",
    "34": "中雨转雨夹雪", "35": "大雨转中雨", "36": "大雨转雨夹雪",
    "37": "中雪转小雪", "38": "中雨转大雪", "39": "中雪转大雪",
    "49": "强浓雾", "53": "霾", "54": "霾", "55": "霾", "56": "霾",
    "57": "大雾", "58": "大雾", "99": "未知", "301": "雨", "302": "雪",
    "303": "雨夹雪", "304": "冻雨", "305": "阵雨", "306": "阵雪", "307": "雾",
    "308": "霜冻", "309": "雨凇", "310": "雪凇", "311": "冰雹", "312": "尘",
    "313": "扬沙", "314": "大风", "315": "风", "316": "热", "317": "冷",
}
AQI_LEVEL = [
    (0, 50, "优"), (50, 100, "良"), (100, 150, "轻度污染"),
    (150, 200, "中度污染"), (200, 300, "重度污染"), (300, 500, "严重污染"),
]

def fetch(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.read()

def gbk_parse(raw):
    # 接口编码不稳定：早期为 GBK，现多返回 UTF-8。逐个尝试，取能解出正常中文者。
    for enc in ("utf-8", "gbk", "gb18030"):
        try:
            t = raw.decode(enc)
        except Exception:
            continue
        if any(k in t for k in ("多云", "江津", "晴", "阴", "小雨", "东风", "南风")):
            return t
    return raw.decode("utf-8", errors="replace")

def parse_var(text, name):
    # 定位 var name = 之后的第一个 {，然后按 var 边界截取到下一个 var 之前
    start = text.find("var " + name + " =")
    if start < 0:
        start = text.find("var " + name + "=")
    if start < 0:
        return None
    body = text[start:]
    # 从第一个 { 开始，找到配对的 }（考虑嵌套括号）
    lb = body.find("{")
    if lb < 0:
        return None
    depth = 0
    end = -1
    in_str = False
    esc = False
    for k in range(lb, len(body)):
        ch = body[k]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = k
                break
    if end < 0:
        return None
    s = body[lb:end + 1]
    s = s.replace("\\/", "/")
    s = re.sub(r"\s+", " ", s)
    try:
        return json.loads(s)
    except Exception:
        return None

def main():
    try:
        raw = fetch(URL)
    except Exception as e:
        print("FETCH_ERROR", e, file=sys.stderr)
        sys.exit(1)
    text = gbk_parse(raw)

    # 实时数据 dataSK
    sk = parse_var(text, "dataSK") or {}
    # 生活指数 dataZS
    zs = parse_var(text, "dataZS") or {}
    # 5日预报 fc
    fc = parse_var(text, "fc") or {}

    now = time.strftime("%Y-%m-%d %H:%M:%S")
    out = {
        "source": "中国天气网 official weather.com.cn",
        "source_type": "CMA",
        "city": CITY_NAME,
        "updated_local": now,
        "updated_ts": int(time.time()),
    }

    # ---- 实况 ----
    w = {}
    try:
        w["temp"] = sk.get("temp")                  # 当前气温
        w["weather"] = sk.get("weather") or "未知"   # 天气现象中文
        w["wd"] = sk.get("WD")
        w["ws"] = sk.get("WS")
        w["humidity"] = sk.get("SD")
        w["pressure"] = sk.get("qy")                # 气压 hPa
        w["vis"] = sk.get("njd")                    # 能见度 km
        w["rain24h"] = (sk.get("rain24h") or "0") + "mm"
        w["obstime"] = sk.get("time")
        w["aqi"] = sk.get("aqi")
        w["aqi_pm25"] = sk.get("aqi_pm25")
    except Exception:
        pass
    out["current"] = w

    # ---- 5 日预报 ----
    days = []
    for f in (fc.get("f") or [])[:5]:
        d = {
            "date": f.get("fi"),
            "label": f.get("fj"),
            "weather": WCODE.get(f.get("fa"), f.get("fa") or "未知"),
            "code": f.get("fa"),
            "high": f.get("fc"),
            "low": f.get("fd"),
        }
        days.append(d)
    out["forecast"] = days

    # ---- AQI 等级 ----
    try:
        aqi = int(w.get("aqi") or 0)
        lv = "优"
        for lo, hi, name in AQI_LEVEL:
            if aqi > lo and aqi <= hi:
                lv = name
                break
        out["aqi_level"] = lv
    except Exception:
        out["aqi_level"] = "未知"

    # ---- 生活指数（dataZS 为扁平结构: ct_name/ct_hint/ct_des_s）----
    indices = {}
    try:
        z = (zs.get("zs") or {}).copy()
        code_alias = {
            "ct": "穿衣", "pl": "空气污染扩散", "co": "舒适度", "uv": "紫外线",
            "gj": "逛街", "cl": "晨练", "lk": "路况", "hc": "划船", "gl": "晒太阳",
            "wc": "风寒", "pk": "放风筝", "ac": "空调", "pj": "啤酒", "yd": "运动",
            "xc": "洗车", "fs": "防晒", "ss": "感冒", "cw": "钓鱼", "dz": "打伞",
        }
        for code, zh in code_alias.items():
            key = code + "_hint"
            if key in z and z.get(code + "_name"):
                indices[zh] = z.get(key, "")
    except Exception:
        pass
    out["indices"] = indices

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print("OK wrote", OUT, "at", now)

if __name__ == "__main__":
    main()