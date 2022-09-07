<h1 align="center">
    naoTimes
</h1>
<p align="center">Bot berbahasa Indonesia untuk membantu tracking garapan fansubber.</p>
<p align="center">Prefix: <b>!</b><br/>Bantuan: <b>!help</b></p>

<h3 align="center"><b>naoTimes Progress Wrapper</b></h3>
<p align="center">Menghubungkan progress garapan dari database bot ke website.</p>s

**Butuh jQuery!**

## Setup Langsung.
1. Selipkan snippet HTML berikut:
    ```html
    <div id='naotimes' class="progress-wrapper">
        <script type="text/javascript" src="https://naotimes.n4o.xyz/assets/js/naoTimes.min.js"></script>
        <script type="text/javascript">
            naoTimesProcess("MASUKAN ID SERVER DISCORD DI SINI"); // Ubah line ini
        </script>
        <h1 class="naotimes-header">Status Garapan</h1>
        <img id='naotimes-loading' width="40" height="40" src='https://puu.sh/DiJzU/6af20efe7e.gif'>
    </div>
    ```
2. Kustomisasi dengan css, listnya ada:
    - **naotimes-header**: teks header dengan tulisan `Status Garapan`
    - **naotimes-animetitle**: bagian judul anime
    - **naotimes-animeprogress**: bagian anime untuk progressnya

## Setup Sendiri

1. Download file `naoTimes.js` atau `naoTimes.min.js`
2. Tambahkan script javascript ke website
3. Selipkan snippet html berikut:
    ```html
    <div id='naotimes' class="progress-wrapper">
        <script type="text/javascript" src="/link/menuju/naoTimes.js"></script> <!-- Ubah line ini -->
        <script type="text/javascript">
            naoTimesProcess("MASUKAN ID SERVER DISCORD DI SINI"); // Ubah line ini
        </script>
        <h1 class="naotimes-header">Status Garapan</h1>
        <img id='naotimes-loading' width="40" height="40" src='https://puu.sh/DiJzU/6af20efe7e.gif'>
    </div>
    ```
4. Kustomisasi dengan css, listnya ada:
    - **naotimes-header**: teks header dengan tulisan `Status Garapan`
    - **naotimes-animetitle**: bagian judul anime
    - **naotimes-animeprogress**: bagian anime untuk progressnya

**Bisa diganti dengan versi minimal dengan mengganti `.js` ke `.min.js`**