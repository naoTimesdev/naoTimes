# Dokumentasi

Dapat dilihat lebih lanjut dengan `!help` dan `!ntadmin`

**Table of content**
* [Informasi](#informasi)
* [Perintah](#perintah)
	* [Perintah User](#perintah-pengunjung)
	* [Perintah Staff](#perintah-staff)
	* [Perintah Admin](#perintah-admin)
* [Lain-Lain](#lain-lain)
* [Demo](#demo)
	* [Perintah User](#perintah-pengunjung-1)
	* [Perintah Staff](#perintah-staff-1)
	* [Perintah Admin](#perintah-admin-1)

# Informasi

Bot ini dibuat dengan Inspirasi dari Bot Aquarius yang ada di server discord GJM dan DDY.

Bot ini dibuat oleh saya sendiri (N4O#8868) pada 21 Maret 2019 karena gabut.

Dijalankan di Heroku server US dengan ping ±40ms

# Perintah

Ini adalah perintah dari module *showtimes* yang merupakan module utama dari bot ini

## Perintah Pengunjung

**!tagih \<judul>**<br>
```
Melihat status terakhir dari Judul yang diberikan, kalau gak nulis judul, akan di list semua garapan yang dikerjain
kalau misalkan dah tamat dikerjain akan muncul `Garapan sudah selesai!` atau semacamnya.
```

**Contoh**:

>!tagih kyuuketsuki

**!jadwal**<br>
```
Melihat seluruh jadwal anime airing yang diambil sebuah Fansub.
```

**!staff \<judul>**<br>
```
Melihat staff yang mengerjakan judul anime tertentu
```

**Contoh**:

>!staff kyuuketsuki

## Perintah Staff

**!beres \<posisi> \<judul>**<br>
```
Menandakan salah satu posisi untuk mengupdate status salah satu garapan
```

**Contoh**:

>!beres tl kyuuketsuki

**judul**: bisa disingkat sesingkat mungkin ;)

**!gakjadi \<posisi> \<judul>**<br>
```
Ini kebalikan dari command !beres
```

**Contoh**:

>!gakjadi tl hitoribocchi

**!rilis \<judul>**
```
Merilis episode dari judul yang dikerjakan
```
**!rilis batch \<jumlah> \<judul>**
```
Merilis jumlah episode tertentu dari judul yang dikerjakan
```
**!rilis semua \<judul>**
```
Merilis semua episode dari judul yang dikerjakan
```

**Contoh**:

>!rilis yuusha

>!rilis batch 3 yuusha

>!rilis semua yuusha

**Note:** <br>
Untuk perintah !rilis batch, terdapat \<jumlah> episode yang mau dirilis.
Penghitungannya adalah **Episode terakhir yang sedang dikerjakan** ditambah **jumlah**.<br>
Misalkan lagi **ngerjain Episode 4**, terus mau **rilis sampai episode 7**<br>
Total dari **Episode 4 sampai 7 ada 4** (4, 5, 6, dan 7)<br>
Maka tulis **jumlahnya 4**

**\<posisi> ada 6, yaitu**:<br>
``tl``: Translator<br>
``tlc``: TLCer (Pemeriksa Terjemahan)<br>
``enc``: Encoder<br>
``ed``: Editor<br>
``tm``: Timer<br>
``ts``: Typesetting (Tata Rias)<br>
``qc``: Quality Check (Pemeriksa Akhir)

## Perintah Admin

**Note**: 
```
Admin ditambahkan manual oleh saya sendiri kedalam Database, jadi silakan PM saya untuk penambahan.
```

Ada 2 command, yaitu:

**!tambahutang**<br>
```
Menambah anime/garapan kedalam database naoTimes
```

Memulai proses penambahan anime ke database.<br>
Ikuti semua prosesnya dan atur sampai benar dan tepat baru masukan ke database

Ada settings yang bisa diubah dalam proses penambahan, yaitu:

**1\. Samakan waktu tayang**<br>
Berguna untuk anime netflix sekali rilis banyak agar tidak terjadi kesalahan ketika waktu sisa sebelum tayangnya.

**Contoh**:

>!tambahutang

**!lupakanutang \<judul>**<br>
```
Drop utang/garapan dan delete dari database
```

**Contoh**:

>!lupakanutang hitoribocchi

**Note:** Jika ada perubahan silakan PM saya di Discord untuk perubahan manual<br>
Jika garapan sudah sampai episode tertentu, bisa PM untuk menghilangkan episode sebelumnya dari DB
{: .notice}

# Lain-Lain

`#progress channel id` merupakan channel tempat Update progress terjadi agar bisa dilihat pengunjung.<br>
Silakan buat channel dan berikan akses ``Send Message`` ke botnya<br>

# Demo

### Perintah Pengunjung

>!tagih

![!tagih](https://puu.sh/D4Y3i/73afd67c2a.gif)
>!jadwal

![!jadwal](https://puu.sh/D4Y4c/4fe5bc26e2.gif)
>!staff

![!staff](https://puu.sh/D4Y6x/ebf16d9b69.gif)

### Perintah Staff

>!beres

![!beres](https://puu.sh/D4Yey/c22ea72c28.gif)
>!gakjadi

![!gakjadi](https://puu.sh/D4Yh9/62647357f7.gif)
>!rilis

![!rilis](https://puu.sh/Daph6/d36dbc3a94.gif)
>!rilis batch

![!rilis batch](https://puu.sh/DapiB/d4fa5c9d38.gif)
>!rilis semua

![!rilis semua](https://puu.sh/Dapks/d479946d71.gif)

### Perintah Admin

>!tambahutang

![!tambahutang](https://i.imgur.com/C4lDXdA.gif)
>!lupakanutang

![!lupakanutang](https://puu.sh/D4YrN/5e92529b3d.gif)