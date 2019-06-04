<h1 align="center">
    naoTimes
</h1>
<p align="center">Bot berbahasa Indonesia untuk membantu tracking garapan fansubber.</p>
<p align="center">Prefix: <b>!</b><br/>Bantuan: <b>!help</b></p>

<p align="center">
  <a href="#invite-bot">Invite</a> •
  <a href="#requirements">Requirements</a> •
  <a href="#setting-up">Setup</a> •
  <a href="#webscript">WebScript</a>
</p>

## Peringatan
**Bot belum siap untuk di setup dan dijalankan, masih ada satu command yang harus dipersiapkan sebelum sepenuhnya open-source**

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
- Python 3.6 (Diusahakan jangan Python 3.7)
- Discord.py (Async version)
- BeautifulSoup4
- aiohttp>=3.4.2
- pytz

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

## WebScript
Kumpulan script website sebagai penghubung antara database dengan website

### [Website Progress](webscript/Website_Progress.md)
Menghubungkan progress garapan dari database bot ke website.