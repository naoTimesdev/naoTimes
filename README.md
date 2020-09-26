<h1 align="center">
    naoTimes
</h1>
<p align="center"><b>versi 2.0.1a</b><br>Bot berbahasa Indonesia untuk membantu tracking garapan fansubber.</p>
<p align="center">Prefix: <b>!</b><br/>Bantuan: <b>!help</b></p>
<p align="center"><img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fserver" data-origin="https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fserver" alt="Guilds"> <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fpengguna" data-origin="https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fpengguna" alt="Users"> <img src="https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fperintah" data-origin="https://img.shields.io/endpoint?url=https%3A%2F%2Fapi.ihateani.me%2Fshield%2Fperintah" alt="Commands"></p>

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

1. Invite bot dengan klik link ini: https://discord.com/oauth2/authorize?client_id=558256913926848537&permissions=805829750&scope=bot

2. Tambah `N4O#8868` sebagai teman dan kirim pesan dengan list berikut:
```
Server ID: 
Admin ID:
#progress announce Channel ID:
```

## Requirements
- Python 3.6+
- MongoDB Server
- Discord.py [>=1.4.0] (Jangan gunakan versi `async`)
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
