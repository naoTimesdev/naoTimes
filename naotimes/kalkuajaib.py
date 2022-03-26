"""
A math helper class for naoTimes.
Based on pyparsing fourFn example:
https://github.com/pyparsing/pyparsing/blob/master/examples/fourFn.py

---

MIT License

Copyright (c) 2019-2021 naoTimesdev

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import math
import operator
import typing as t

import pyparsing as pp

EPSILON = 1e-12

__all__ = ("GagalKalkulasi", "KalkulatorAjaib")


class GagalKalkulasi(SyntaxError):
    def __init__(self, teks):
        self.angka = teks
        super().__init__(f"Gagal melakukan kalkulasi pada `{teks}`")


class KalkulatorAjaib:
    """Sebuah objek Kalkulator yang dapat melakukan kalkulasi dari string

    Menggunakan modul pyparsing, base code merupakan contoh dari example fourFn
    https://github.com/pyparsing/pyparsing/blob/master/examples/fourFn.py

    Cara pakai:
    ```py
    hasil = KalkulatorAjaib.kalkulasi("9 + 11")
    print(hasil)
    ```
    """

    e = pp.CaselessKeyword("E")
    pi = pp.CaselessKeyword("PI")

    fnumber = pp.Regex(r"[+-]?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?")
    ident = pp.Word(pp.alphas, pp.alphanums + "_$")

    plus, minus, mul, div = map(pp.Literal, "+-*/")
    lpar, rpar = map(pp.Suppress, "()")
    addop = plus | minus
    mulop = mul | div
    expop = pp.Literal("^")

    opn = {
        "+": operator.add,
        "-": operator.sub,
        "*": operator.mul,
        "/": operator.truediv,
        "^": operator.pow,
    }

    fn = {
        "sin": math.sin,
        "cos": math.cos,
        "tan": math.tan,
        "exp": math.exp,
        "abs": abs,
        "trunc": int,
        "round": round,
        "sgn": lambda a: -1 if a < -EPSILON else 1 if a > EPSILON else 0,
        "multiply": lambda a, b: a * b,
        "hypot": math.hypot,
    }

    def __init__(self) -> None:
        self.expr_stack = []

        def push_first(toks):
            self.expr_stack.append(toks[0])

        def push_unary_minus(tokens):
            for token in tokens:
                if token == "-":
                    self.expr_stack.append("unary -")
                else:
                    break

        expr = pp.Forward()
        expr_list = pp.delimitedList(pp.Group(expr))

        def insert_fn_argcount_tuple(t):
            fn = t.pop(0)
            num_args = len(t[0])
            t.insert(0, (fn, num_args))

        fn_call = (self.ident + self.lpar - pp.Group(expr_list) + self.rpar).setParseAction(
            insert_fn_argcount_tuple
        )

        atom = (
            self.addop[...]
            + (
                (fn_call | self.pi | self.e | self.fnumber | self.ident).setParseAction(push_first)
                | pp.Group(self.lpar + expr + self.rpar)
            )
        ).setParseAction(push_unary_minus)

        factor = pp.Forward()
        factor <<= atom + (self.expop + factor).setParseAction(push_first)[...]
        term = factor + (self.mulop + factor).setParseAction(push_first)[...]
        expr <<= term + (self.addop + term).setParseAction(push_first)[...]
        self.expr: pp.Forward = expr

    def _evaluate_stack(self, stack):
        op, num_args = stack.pop(), 0
        if isinstance(op, tuple):
            op, num_args = op
        if op == "unary -":
            return -self._evaluate_stack(stack)
        if op in "+-*/^":
            op2 = self._evaluate_stack(stack)
            op1 = self._evaluate_stack(stack)
            return self.opn[op](op1, op2)
        elif op == "PI":
            return math.pi
        elif op == "E":
            return math.e
        elif op in self.fn:
            args = reversed([self._evaluate_stack(stack) for _ in range(num_args)])
            return self.fn[op](*args)
        elif op[0].isalpha():
            raise SyntaxError("Identifier '%s' tidak diketahui" % op)
        else:
            try:
                return int(op)
            except ValueError:
                return float(op)

    def hitung(self, kalkulasikan: str) -> t.Union[int, float]:
        """Melakukan kalkulasi terhadap string input

        :param kalkulasikan: string untuk dikalkulasikan
        :type kalkulasikan: str
        :raises GagalKalkulasi: Jika gagal evaluasi ekspresi matematikanya.
        :return: hasil kalkulasi
        :rtype: t.Union[int, float]
        """
        try:
            self.expr.parseString(kalkulasikan, parseAll=True)
        except pp.ParseException as pe:
            raise SyntaxError("Gagal melakukan parsing, " + str(pe))
        try:
            results = self._evaluate_stack(self.expr_stack)
        except SyntaxError:
            raise GagalKalkulasi(kalkulasikan)
        return results

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
        try:
            calc.expr.parse_string(kalkulasikan, parseAll=True)
        except pp.ParseException as pe:
            raise SyntaxError("Gagal melakukan parsing, " + str(pe))
        try:
            results = calc._evaluate_stack(calc.expr_stack)
        except SyntaxError:
            raise GagalKalkulasi(kalkulasikan)
        return results
