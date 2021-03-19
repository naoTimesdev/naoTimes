import typing as t
from string import digits, ascii_letters

safe_symbols = "+=-/*."
concat_symbol = "()[]"
symbols = safe_symbols + concat_symbol


class GagalKalkulasi(SyntaxError):
    def __init__(self, teks):
        self.angka = teks
        super().__init__(f"Gagal melakukan kalkulasi pada `{teks}`")


def issymbol(text: str) -> bool:
    """Cek jika teks mengandung simbol matematika atau semacamnya"""
    valid = True
    for txt in text:
        if txt not in safe_symbols:
            valid = False
            break
    return valid


class KalkulatorAjaib:
    """Sebuah objek Kalkulator yang dapat melakukan kalkulasi dari string

    Sangat sampah, karena gak mau pake external module.

    Cara pakai:
    ```py
    hasil = KalkulatorAjaib.kalkulasi("9 + 11")
    print(hasil)
    ```
    """

    @staticmethod
    def _tokenize(string_val: str) -> t.List[str]:
        """Tokenisasi string menjadi koleksi string

        :param string_val: string input
        :type string_val: str
        :return: hasil tokenisasi
        :rtype: t.List[str]
        """
        explode_str = list(string_val)
        token = []
        current_txt = ""
        current_type = ""
        for txt in explode_str:
            if txt in digits:
                if current_txt and current_type not in ["d", "c"]:
                    token.append(current_txt)
                    current_txt = txt
                    current_type = "d"
                else:
                    current_txt += txt
                    current_type = "d"
            elif txt in ascii_letters:
                if current_txt and current_type not in ["s", "c"]:
                    token.append(current_txt)
                    current_txt = txt
                    current_type = "s"
                else:
                    current_txt += txt
                    current_type = "s"
            elif txt in concat_symbol:
                current_type = "c"
                token.append(current_txt)
                current_txt = txt
            elif txt in safe_symbols:
                if txt == "." and current_type == "d":
                    current_txt += txt
                    continue
                if current_txt and current_txt not in ["b", "c"]:
                    token.append(current_txt)
                    current_txt = txt
                    current_type = "b"
                else:
                    current_txt += txt
                    current_type = "b"
            elif txt == " ":
                if current_txt and current_type not in ["sp", "c"]:
                    token.append(current_txt)
                    current_txt = ""
                    current_type = "sp"
                else:
                    current_txt += txt
                    current_type = "sp"
        if current_txt:
            token.append(current_txt)
        return token

    def __sanitize(self, string_val: str) -> t.List[str]:
        """Sanitasi string input
        Mempastikan tidak ada input yang memungkinkan eksekusi RCE.

        :param string_val: string input
        :type string_val: str
        :return: sanitized input
        :rtype: t.List[str]
        """
        tokenized = self._tokenize(string_val)
        sanitized = []
        allowed_func = ["round"]
        for token in tokenized:
            token = token.strip()
            if token in ["", " "]:
                continue
            if token in concat_symbol:
                sanitized.append(token)
                continue
            append_start = ""
            append_end = ""
            if token.startswith("(") or token.startswith("["):
                append_start = token[0]
                token = token[1:]
            if token.endswith(")") or token.endswith("]"):
                append_end = token[-1]
                token = token[:-1]
            try:
                float(token)
                sanitized.append(f"{append_start}{token}{append_end}")
                continue
            except ValueError:
                pass
            if issymbol(token):
                sanitized.append(token)
                continue
            if len(token) == 1:
                sanitized.append(f"{append_start}{token}{append_end}")
                continue
            if token in allowed_func:
                sanitized.append(f"{append_start}{token}{append_end}")
                continue
        return sanitized

    @classmethod
    def kalkulasi(cls, kalkulasikan: str) -> t.Union[int, float]:
        """Melakukan kalkulasi terhadap string input

        :param kalkulasikan: string untuk dikalkulasikan
        :type kalkulasikan: str
        :raises GagalKalkulasi: Jika gagal evaluasi ekspresi matematikanya.
        :return: hasil kalkulasi
        :rtype: t.Union[int, float]
        """
        calc = cls()
        sanitized = calc.__sanitize(kalkulasikan)
        try:
            hasil = eval("".join(sanitized))
        except SyntaxError:
            raise GagalKalkulasi("".join(sanitized))
        return hasil
