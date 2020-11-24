<h1 align="center">
    naoTimes
</h1>
<p align="center"><b>versi 2.0.1a</b><br>Bot berbahasa Indonesia untuk membantu tracking garapan fansubber.</p>
<p align="center">Prefix: <b>!</b><br/>Bantuan: <b>!help</b></p>
<p align="center"><img src="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fserver" data-origin="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fserver" alt="Guilds"> <img src="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fpengguna" data-origin="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fpengguna" alt="Users"> <img src="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fperintah" data-origin="https://img.shields.io/endpoint?color=%231c7d9a&logo=discord&logoColor=white&style=for-the-badge&url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fperintah" alt="Commands"> <img src="https://img.shields.io/uptimerobot/status/m786469671-606ba8f8deaf00978879eb7d?style=for-the-badge" data-src="https://img.shields.io/uptimerobot/status/m786469671-606ba8f8deaf00978879eb7d?style=for-the-badge" alt="Bot Status"></p>

<p align="center">
    <a href="#invite-bot">Invite</a> •
    <a href="#requirements">Requirements</a> •
    <a href="#setting-up">Setup</a> •
    <a href="#webscript">WebScript</a> •
    <a href="https://naotimes.n4o.xyz">Dokumentasi</a>
</p>

<p align="center">:warning: <b>Laporkan kesalahan di <a href="https://github.com/noaione/naoTimes/issues">Issues</a></b> :warning:</p>

## Invite bot
Males setup sendiri? Mau simple dan cepet?

1. Invite bot dengan klik link ini: https://naoti.me/invite

2. Tambah `N4O#8868` sebagai teman dan kirim pesan dengan list berikut:
```
Server ID: 
Admin ID:
#progress announce Channel ID:
```

## Discord Gateway Intents
~~Akan segera di support oleh bot, untuk sementara jangan update ke discord.py versi 1.5.0~~<br>
Support telah ditambahkan, silakan pakai versi 1.5.0 jika mau.

Jika sudah situ upgrade, silakan aktifkan **Privileged Gateway Intents** untuk **Server Members Intent**<br>
Bisa ditemukan di bagian settings Bot di laman [Discord Developer Portal](https://discord.com/developers/).

## Requirements
- Python 3.6+
- MongoDB Server
- Discord.py [>=1.4,<1.5] (Jangan gunakan versi `async`, versi 1.5.0 optional sampai Discord drop support.)
- aiohttp [>=3.6.2]
- motor [==2.2.0]
- BeautifulSoup4 [==4.9.1]
- aiofiles [==0.5.0]
- feedparser [==5.2.1]
- ujson [==1.3.5]
- kbbi [>=0.4.1]
- pysubs2 [>=0.2.4]
- textblob [>=0.15.3]
- markdownify [>=0.4.1]

## Setting up
*Rewriting...*

## WebScript
Kumpulan script website sebagai penghubung antara database dengan website

### [Website Progress](webscript/Website_Progress.md)
Menghubungkan progress garapan dari database bot ke website.
