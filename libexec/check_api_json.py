#!/usr/bin/env python3
"""check_api_json.py - interroge une API HTTP(S) JSON et vérifie un champ.

Usage :
  check_api_json.py -u URL -k CHEMIN [-e VALEUR | -w SEUIL -c SEUIL]
                    [--min] [--token-file FICHIER] [-H 'En-tête: valeur'] [-t SECONDES]

  -k  chemin du champ dans le JSON, séparé par des points ; un entier désigne
      un élément de liste : "status", "data.items.0.state", "checks.db.latency"
  -e  valeur attendue (comparaison textuelle) : CRITICAL si différente
  -w/-c  seuils numériques : WARNING/CRITICAL si la valeur les atteint
  --min   les seuils sont des minimums : alerte si la valeur descend à ou
          sous le seuil (quota restant, espace libre, nombre de nœuds…)
  --token-file  fichier contenant un jeton envoyé en "Authorization: Bearer"
                (jamais le jeton lui-même en argument : il serait visible
                dans la liste des processus et dans Thruk)

Codes retour : 0 OK, 1 WARNING, 2 CRITICAL, 3 UNKNOWN.
Bibliothèque standard uniquement : fonctionne tel quel dans l'image Shinken.
"""
import argparse
import json
import ssl
import sys
import time
import urllib.error
import urllib.request

OK, WARNING, CRITICAL, UNKNOWN = 0, 1, 2, 3
LABELS = {OK: "OK", WARNING: "WARNING", CRITICAL: "CRITICAL", UNKNOWN: "UNKNOWN"}


def sortir(code, message, perf=""):
    print(f"API {LABELS[code]} - {message}" + (f" | {perf}" if perf else ""))
    sys.exit(code)


def extraire(document, chemin):
    valeur = document
    for morceau in chemin.split("."):
        valeur = valeur[int(morceau)] if isinstance(valeur, list) else valeur[morceau]
    return valeur


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("-u", "--url", required=True)
    p.add_argument("-k", "--key", required=True, help="chemin du champ JSON")
    p.add_argument("-e", "--expect")
    p.add_argument("-w", "--warning", type=float)
    p.add_argument("-c", "--critical", type=float)
    p.add_argument("--min", action="store_true",
                   help="seuils minimums : alerte si la valeur est en dessous")
    p.add_argument("-t", "--timeout", type=float, default=10)
    p.add_argument("-H", "--header", action="append", default=[])
    p.add_argument("--token-file")
    p.add_argument("--insecure", action="store_true",
                   help="ne pas vérifier le certificat (à éviter)")
    args = p.parse_args()

    requete = urllib.request.Request(args.url, headers={"Accept": "application/json"})
    for entete in args.header:
        nom, _, valeur = entete.partition(":")
        requete.add_header(nom.strip(), valeur.strip())
    if args.token_file:
        try:
            with open(args.token_file, encoding="utf-8") as f:
                requete.add_header("Authorization", "Bearer " + f.read().strip())
        except OSError as exc:
            sortir(UNKNOWN, f"jeton illisible : {exc}")

    contexte = ssl._create_unverified_context() if args.insecure else None
    debut = time.monotonic()
    try:
        with urllib.request.urlopen(requete, timeout=args.timeout, context=contexte) as rep:
            corps = rep.read()
            statut = rep.status
    except urllib.error.HTTPError as exc:
        sortir(CRITICAL, f"HTTP {exc.code} {exc.reason} sur {args.url}")
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raison = getattr(exc, "reason", exc)
        sortir(CRITICAL, f"injoignable : {raison}")
    duree = time.monotonic() - debut
    perf = f"time={duree:.3f}s;;;0;{args.timeout:g}"

    try:
        document = json.loads(corps)
        valeur = extraire(document, args.key)
    except json.JSONDecodeError:
        sortir(CRITICAL, f"HTTP {statut}, réponse non JSON", perf)
    except (KeyError, IndexError, ValueError, TypeError):
        sortir(UNKNOWN, f"champ '{args.key}' absent de la réponse", perf)

    if args.expect is not None:
        if str(valeur) != args.expect:
            sortir(CRITICAL, f"{args.key}={valeur!r}, attendu {args.expect!r}", perf)
        sortir(OK, f"{args.key}={valeur!r} en {duree:.2f}s", perf)

    if args.warning is not None or args.critical is not None:
        try:
            nombre = float(valeur)
        except (TypeError, ValueError):
            sortir(UNKNOWN, f"{args.key}={valeur!r} n'est pas un nombre", perf)
        perf += f" '{args.key}'={nombre:g};{'' if args.warning is None else f'{args.warning:g}'}" \
                f";{'' if args.critical is None else f'{args.critical:g}'}"
        def franchi(seuil):
            return seuil is not None and (nombre <= seuil if args.min else nombre >= seuil)
        if franchi(args.critical):
            sortir(CRITICAL, f"{args.key}={nombre:g} (seuil {args.critical:g})", perf)
        if franchi(args.warning):
            sortir(WARNING, f"{args.key}={nombre:g} (seuil {args.warning:g})", perf)
        sortir(OK, f"{args.key}={nombre:g}", perf)

    sortir(OK, f"{args.key}={valeur!r} en {duree:.2f}s", perf)


if __name__ == "__main__":
    main()
