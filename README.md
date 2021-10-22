<h1 align="center">
    naoTimes
</h1>
<p align="center"><b>versi 3.0.0</b><br>Bot berbahasa Indonesia untuk membantu tracking garapan fansubber.</p>
<p align="center">Prefix: <b>!</b><br/>Bantuan: <b>!help</b></p>
<p align="center"><img src="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fserver" data-origin="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fserver" alt="Guilds"> <img src="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fpengguna" data-origin="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fpengguna" alt="Users"> <img src="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fperintah" data-origin="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fperintah" alt="Commands"> <img src="https://img.shields.io/uptimerobot/status/m786469671-606ba8f8deaf00978879eb7d?style=for-the-badge" data-src="https://img.shields.io/uptimerobot/status/m786469671-606ba8f8deaf00978879eb7d?style=for-the-badge" alt="Bot Status"></p>

<p align="center">
    <a href="#invite-bot">Invite</a> •
    <a href="#requirements">Requirements</a> •
    <a href="#setting-up">Setup</a> •
    <a href="https://naoti.me/docs/">Dokumentasi</a> •
    <a href="https://naoti.me/docs/changelog">Changelog</a>
</p>

<p align="center">⚠ <b>Laporkan kesalahan di <a href="https://github.com/noaione/naoTimes/issues">Issues</a></b> ⚠</p>

## Invite bot
Males setup sendiri? Mau simple dan cepet?

1. Invite bot dengan klik link ini: https://naoti.me/invite
2. Jika anda ingin menggunakan fitur Showtimes, silakan daftar di: https://panel.naoti.me/registrasi
3. Setelah itu bisa jalankan `!showui` untuk mendapatkan password.

## Discord Gateway Intents
Agar naoTimes dapat bekerja dengan benar, anda membutuhkan **Privileged Intents** ini aktif di laman [Discord Developer Portal](https://discord.com/developers/).

- Server Members Intent
Dibutuhkan agar beberapa fitur moderasi dan Showtimes dapat bekerja.
- Presence Intent
Dibutuhkan agar fitur seperti user info dan server info dapat bekerja dengan benar dan akurat.

## Requirements
- Python 3.8+
- Redis server
- MongoDB server (Bisa host di Atlas, ini untuk Showtimes)
- Discord Bot Token
- `libmagic1`

Untuk module, refer ke file `requirements.txt`

## Setting up
1. Install Python 3.8, siapkan redis server anda dan jalankan (silakan cari di Google)
   - Jika anda ingin menggunakan Showtimes, mohon siapkan MongoDB database.
2. Buat virtualenv baru dengan cara `virtualenv env`
3. Masuk ke virtualenv tersebut
   - Windows: `.\env\Scripts\activate`
   - Linux/macOS: `source ./env/bin/activate`
4. Install requirements dengan cara: `pip install -c constrains.txt -r requirements.txt`
   - Disarankan gunakan `-c constraints.txt` jika anda menggunakan pip 20.3 keatas
5. Install libmagic
   - Windows: Harusnya sudah terinstall ketika menggunakan `pip install`
   - Windows alt: Install dengan pip: `pip install python-magic-bin`
   - Debian/Ubuntu: `sudo apt-get install libmagic1` 
   - OSX/macOS: `brew install libmagic` atau `port install file`
6. Buat config baru mengikuti `config.json.example`
   - Jika anda tidak punya, bisa diabaikan aja.
   - Silakan refer ke [Konfigurasi](#konfigurasi)
7. Jalankan bot dengan `python bot.py`
8. Invite bot dengan permission berikut:
   - Manage Server
   - Manage Channels
   - Manage Roles
   - Kick Members
   - Ban Members
   - Manage Nicknames
   - Change Nickname
   - Manage Emojis and Stickers
   - View Audit Log
   - Read Messages
   - Send Messages
   - Manage Messages
   - Embed Links
   - Attach Files
   - Read Messages History
   - Mention @eveyone, @here, and All Roles
   - Add Reactions
   - Use External Emojis
   - Mute Members
   - Deafen Members
9.  naoTimes sudah siap, anda bisa mengaktifkan [fitur opsional](#fitur-opsional)

Untuk menjalankan naoTimes di mode production, mohon buat file kosong dengan nama `authorize_prod`
di folder utama.

![Sample](https://p.ihateani.me/juuunxbt.png)

Atau jalankan bot di dev mode dengan menambahkan argumen `-dev` setelah `python bot.py`

```sh
(env) $ python bot.py -dev
```

## Konfigurasi
Berikut adalah contoh konfigurasi naoTimes:
```json
{
    "bot_id": "",
    "bot_token": "",
    "default_prefix": "!",
    "slash_test_guild": null,
    "vndb": {
        "username": "",
        "password": ""
    },
    "mongodb": {
        "ip_hostname": "localhost",
        "port": 27017,
        "dbname": "naotimesdb",
        "tls": false,
        "auth": ""
    },
    "redisdb": {
        "ip_hostname": "127.0.0.1",
        "port": 6379,
        "password": null
    },
    "socketserver": {
        "port": 25670,
        "password": null
    },
    "kbbi": {
        "email": "",
        "password": ""
    },
    "fansubdb": {
        "username": "",
        "password": ""
    },
    "weather_data": {
        "openweatherapi": "",
        "opencageapi": ""
    },
    "wolfram": {
        "app_id": ""
    },
    "merriam_webster": {
        "dictionary": "",
        "thesaurus": ""
    },
    "steam_api_key": ""
}
```

- `bot_id` merupakan "Client ID" aplikasi anda, dapat diliat dibagian `OAuth2`
- `bot_token` merupakan token yang anda buat di bagian `Bot`
- `default_prefix` ini merupakan prefix global untuk bot naoTimes, default adalah `!`
- `slash_test_guild` sebuah server sebagai test guild untuk /slash command, ini akan mastiin semua /slash command bisa bekerja!
- `vndb.username`/`vndb.password` merupakan username/password akun [VNDB](https://vndb.org/) anda, cukup berikan informasinya jika anda ingin menggunakan fitur [VNDB](https://vndb.org/).
- `mongodb` merupakan konfigurasi MongoDB, jika anda tidak ingin menggunakannya mohon hapus
  - `ip_hostname` merupakan IP/domain database anda
  - `port` merupakan port yang dipakai untuk database anda (default `27017`)
  - `dbname` nama databasenya, contoh `naotimes`
  - `tls` jika anda menggunakan SSL, jika host di MongoDB Atlas, ubah jadi `true`
  - `auth` merupakan username/password untuk akses database anda (bisa dikosongkan), formatnya adalah: `username:password`
- `redisdb` merupakan konfigurasi Redis anda
  - `ip_hostname` merupakan IP/domain database redis anda
  - `port` merupakan port yang dipakai untuk database anda (default `6379`)
  - `password` password untuk akses redis anda (bisa dikosongkan)
- `socketserver` merupakan socket server di mana anda bisa menggunakannya untuk akses bot dengan menggunakan socket (bukan websocket)
  - `port` port untuk run socket servernya (default: 25670)
  - `password` jika anda butuh password untuk akses
- `fansubdb` fitur integrasi Showtimes dengan FansubDB (bisa dikosongkan)
- `weather_data` API key untuk fitur cuaca naoTimes, bisa dikosongkan
  - `openweatherapi` API key OpenWeatherMap (https://openweathermap.org/)
  - `opencageapi` API key untuk OpenCage Geocoding (https://opencagedata.com/)
- `wolfram` App ID untuk fitur Wolfram, bisa dikosongkan jika tidak butuh
- `merriam_webster` API key untuk fitur definisi kata dan tesaurus kata bahasa inggris melalui [Merriam Webster](https://dictionaryapi.com/), disarankan pilih yang Collegiate (bisa dikosongkan)
  - `dictionary` API key untuk akses Collegiate dictionary
  - `thesaurus` API key untuk akses Collegiate thesaurus
- `steam_api_key` developer API key Steam API, dibutuhkan untuk akses beberapa fitur naoTimes (seperti games search di Steam, dsb), bisa dikosongkan jika tidak perlu.


### Fitur opsional
naoTimes juga ada fitur opsional yang bisa diaktifkan ketikan bot sudah aktif.

1. Ticketing system
Fitur ini dipakai untuk user yang memiliki masalah dengan bot, ini akan dilaporkan ke server anda.
Aktifkan dengan: `!enableticket`

2. Error logging
Fitur di mana anda bisa log masalah bot ke sebuah server, jika tidak ada akan dikirim ke DM anda.
Aktifkan dengan menambah opsi `error_logger` ke `config.json` anda dengan isi channel ID-nya.
Contoh:
```json
[...]
    "steam_api_key": "XXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
    "error_logger": 12345678090123
[...]
```

3. Sentry Logging
Fitur di mana anda dapat mengupload semua log masalah anda ke Sentry.
Untuk menggunakannya cukup tambahkan config ini ke file `config.json` anda.
```json
[...]
    "statistics": {
        "sentry_dsn": "https://1234567890abcdefghijklmn.ingest.sentry.io/XXXXXX"
    }
[...]
```

Silakan ganti `sentry_dsn` sesuai DSN anda.

## Donasi
Anda dapat mensupport naoTimes dan mendapatkan fitur Premium.
Dengan donasi mulai dari 1$ atau 15000, anda dapat mengakses fitur premium berikut.

1. FansubRSS Premium
   - 3 RSS
   - Rate refresh lebih cepat (2 menit dibanding 5 menit)
2. Premium support

Silakan donasi ke link berikut:
- [Trakteer](https://trakteer.id/noaione/tip) (Indonesia) [IDR]
- [Ko-fi](https://ko-fi.com/noaione) (Lain-lain) [USD]

## Lisensi
naoTimes dilisensi dengan lisensi MIT.
Logo yang dipakai oleh naoTimes merupakan karakter `Hitori Bocchi` dari anime `Hitori Bocchi no Marumaru Seikatsu`, logo tersebut merupakan hak cipta pembuatnya.
