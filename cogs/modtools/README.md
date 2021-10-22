# Cogs: Moderation Tools
Koleksi alat moderasi untuk peladen yang menggunakan naoTimes!

- automod
- channel
- guild
- member

**Gunakan `!help <nama perintah>` untuk info lebih lanjut!**

## automod.py
Merupakan alat untuk melakukan moderasi otomatis untuk kata-kata yang menurut anda dilarang.

Untuk kata-kata yang dilarang secara *default*, mohon cek file `automod.py` dan line `DEFAULT_AUTOMOD_WORDS`

### Perintah
- `!automod`: aktifkan sistem automod
- `!automod tambah`: tambahkan kata baru untuk automod
- `!automod matikan`: Matikan automod
- `!automod info`: cek sedikit informasi automod untuk peladen anda

## channel.py
Merupakan alat moderasi untuk kanal teks peladen

### Perintah
- `!lockdown`: Tutup sebuah kanal agar pengguna biasa tidak bisa *nge-chat*
- `!unlock`: Buka kembali kanal yang dilockdown
- `!lockall`: Tutup semua kanal teks
- `!unlockall`: Buka kembali semua kanal teks yang dilockdown
- `!slowmode`: Aktifkan slowmode pada sebuah kanal

## guild.py
Merupakan alat untuk melakukan moderasi peladen (server related stuff)

### Perintah
- `!serverlog`: Aktifkan pencatatan moderasi untuk peladen

## member.py
Merupakan alat untuk moderasi anggota peladen

### Perintah
- `!shadowban`: Ban anggota yang belum join dari peladen
- `!unshadowban`: Unban anggota yang kena `!shadowban`
- `!mute`: Mute anggota peladen
- TODO `!unmute`: Unmute anggota yang terkena `!mute`

*(c) 2019-2021 naoTimesdev*