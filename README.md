<h1 align="center">
    naoTimes
</h1>
<p align="center"><b>versi 2.0.0</b><br>Bot berbahasa Indonesia untuk membantu tracking garapan fansubber.</p>
<p align="center">Prefix: <b>!</b><br/>Bantuan: <b>!help</b></p>

<p align="center">
    <a href="#invite-bot">Invite</a> •
    <a href="#requirements">Requirements</a> •
    <a href="#setting-up">Setup</a> •
    <a href="#webscript">WebScript</a> •
    <a href="https://blog.n4o.xyz/blog/naotimes/">Dokumentasi</a>
</p>

<p align="center">:warning: <b>Laporkan kesalahan di <a href="https://github.com/noaione/naoTimes/issues">Issues</a></b> :warning:</p>

## Informasi
Versi rewrite, bot akan direwrite yang akan menggunakan discord.py versi terbaru
Fitur tambahan (Rencana):
- RSS (Untuk rilisan)

## Invite bot
Males setup sendiri? Mau simple dan cepet?

1. Invite bot dengan klik link ini: https://discordapp.com/api/oauth2/authorize?client_id=558256913926848537&permissions=268823632&scope=bot

2. Tambah `N4O#8868` sebagai teman dan kirim pesan dengan list berikut:
```
Server ID: 
Admin ID:
#progress announce Channel ID:
```

## Requirements
- Python 3.6+ (Diusahakan jangan Python 3.7)
- Discord.py
- BeautifulSoup4
- aiohttp>=3.4.2
- kbbi
- pytz
- pysubs2
- textblob


Bagi pengguna Python 3.7, cek isu berikut: [Rapptz/discord.py#1249](https://github.com/Rapptz/discord.py/issues/1249)

Silakan cek commit discord.py berikut: [Rapptz/discord.py@1863a1c](https://github.com/Rapptz/discord.py/commit/1863a1c6636f53592519320a173ec9573c090c0b)

Update requirements dengan
```bash
pip install -U https://github.com/Rapptz/discord.py/archive/async.zip
```

## Setting up
1. Clone/Download repo ini
2. Buat gist private/public dengan info berikut:
    - Filename: `nao_showtimes.json`
    - Content: Isi asal, disarankan -> `{}`
3. Rename file `config.json.example` menjadi `config.json` dan isi:
    - **username**: **Username github** *bukan* Email github
    - **password**: Password github
    - **bot_token**: Token bot discord
    - **main_server**: Isi dengan ID server anda sendiri
    - **owner_id**: Isi dengan ID discord anda
4. Invite bot anda dengan permission minimal dibawah ini
    - Manage Messages
    - Manage Roles
    - Manage Channels
    - View Channels
    - Read Message History
    - Use External Emojis
    - Embed Links
    - Send Message
    - Attach Files
    - Add Reactions
5. Jalankan bot dengan `python bot.py`
6. Aktifkan naoTimes dengan `!ntadmin initiate`
7. Ikuti perintahnnya dan klik react `centang` jika sudah benar semua
8. Bot siap digunakan, silakan liat dokumentasinya [di sini](https://blog.n4o.xyz/blog/naotimes/) atau [di sini](DOKUMENTASI.md)

**Note**

Kalau dijalankan di Heroku, atur `gist_id` secara manual dan buat gist sesuai langkah 2<br>
Tetapi isi contentnya seperti ini:
```json
{
    "serverowner": [
        "ID_ADMIN_SERVER_AWAL"
    ],
    "SERVER_ID_AWAL": {
        "serverowner": [
            "ID_ADMIN_SERVER_AWAL"
        ],
        "announce_channel": "ID_CHANNEL_PROGRESS",
        "anime": {},
        "alias": {}
    }
}
```

**Contoh**:
```json
{
    "serverowner": [
        "466469077444067372"
    ],
    "472705451117641729": {
        "serverowner": [
            "466469077444067372"
        ],
        "announce_channel": "558321533060251664",
        "anime": {},
        "alias": {}
    }
}
```

Lalu copy **`Gist IDnya`** dan masukan ke **`config.json`**

## WebScript
Kumpulan script website sebagai penghubung antara database dengan website

### [Website Progress](webscript/Website_Progress.md)
Menghubungkan progress garapan dari database bot ke website.
