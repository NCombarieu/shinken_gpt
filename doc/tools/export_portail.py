#!/usr/bin/env python3
"""Exporte doc/ vers le corpus d'un portail documentaire (documentation-supervision).

Usage :
    python3 doc/tools/export_portail.py <dossier docs/ du portail> [--domaine shinken]

Le script (re)crée <docs>/<domaine>/ à partir de doc/ :

* ajoute à chaque fiche le front matter exigé par le portail (titre, catégorie,
  type, niveau, version, date, responsable, statut, ordre, résumé) ;
* renomme les README.md en index.md (page d'accueil de la catégorie) et écrit
  un _domain.yml par dossier ;
* réécrit les liens relatifs entre fiches en adresses du portail
  (/doc/<domaine>/<chemin>), en convertissant les ancres GitHub en ancres du
  portail (Python-Markdown retire les accents) ;
* réécrit les liens vers le reste du dépôt (etc/, deploy/, Changelog…) en
  liens vers GitHub.

doc/revue/ (audit historique) et doc/tools/ ne sont pas exportés. Le dossier
cible est entièrement remplacé : ne pas y faire de modifications à la main,
corriger doc/ puis relancer l'export.
"""
import argparse
import datetime
import os
import re
import shutil
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOC = os.path.join(ROOT, "doc")
GITHUB = "https://github.com/NCombarieu/shinken_gpt/blob/modernize/podman-python3/"
EXCLUS = ("revue", "tools")

# Libellé de catégorie, niveau par défaut et métadonnées de chaque dossier.
DOSSIERS = {
    "": ("Shinken", "debutant", {
        "title": "Shinken",
        "description": "Moteur de supervision Shinken porté en Python 3 et déployé "
                       "en conteneurs Podman : administration de la supervision, "
                       "exécution des checks, recettes, Thruk, exploitation du serveur, "
                       "migration et développement.",
        "icon": "radar", "order": 15}),
    "admin": ("Shinken / Administration", "intermediaire", {
        "title": "Administration de la supervision",
        "description": "Configurer la supervision : hôtes, services, contacts, "
                       "exécution des checks, checks à distance, plugins, notifications.",
        "icon": "folder", "order": 10}),
    "admin/recettes": ("Shinken / Administration / Recettes", "intermediaire", {
        "title": "Recettes",
        "description": "Procédures complètes par type de cible : Linux (SSH, NRPE), "
                       "Windows, SNMP, HTTP/TLS, API REST, DNS, bases de données.",
        "icon": "folder", "order": 30}),
    "admin/reference": ("Shinken / Administration / Référence", "intermediaire", {
        "title": "Référence de la configuration",
        "description": "Toutes les directives de chaque objet, les macros et les "
                       "commandes externes, générées depuis le code.",
        "icon": "folder", "order": 40}),
    "thruk": ("Shinken / Thruk", "intermediaire", {
        "title": "Thruk",
        "description": "L'interface web : conteneur OMD, connexion Livestatus, "
                       "comptes et droits, exposition et dépannage.",
        "icon": "folder", "order": 20}),
    "exploitation": ("Shinken / Exploitation", "intermediaire", {
        "title": "Exploitation du serveur",
        "description": "Installer, configurer, sauvegarder, mettre à jour, sécuriser "
                       "et dépanner Shinken sous Podman ; processus, déploiement Puppet.",
        "icon": "folder", "order": 30}),
    "dev": ("Shinken / Développement", "avance", {
        "title": "Développement",
        "description": "Architecture du code, protocole entre daemons, écriture de "
                       "modules, historique du portage Python 3.",
        "icon": "folder", "order": 50}),
}

NIVEAUX_PAR_FICHIER = {
    "migration-depuis-shinken-master.md": "avance",
}

_LIEN = re.compile(r"(?<!!)\[([^\]]*)\]\(([^)\s]+)\)")
_TITRE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def ancre_github(titre):
    titre = re.sub(r"[`*_]", "", titre).strip().lower()
    titre = re.sub(r"[^\w\- ]", "", titre)
    return titre.replace(" ", "-")


def ancre_portail(titre):
    """Même calcul que markdown.extensions.toc.slugify."""
    titre = re.sub(r"[`*]", "", titre)
    titre = unicodedata.normalize("NFKD", titre).encode("ascii", "ignore").decode("ascii")
    titre = re.sub(r"[^\w\s-]", "", titre).strip().lower()
    return re.sub(r"[-\s]+", "-", titre)


def titres(chemin):
    resultat, dans_code = [], False
    with open(chemin, encoding="utf-8") as f:
        for ligne in f:
            if ligne.lstrip().startswith("```"):
                dans_code = not dans_code
                continue
            m = None if dans_code else _TITRE.match(ligne)
            if m:
                resultat.append(m.group(2))
    return resultat


def convertir_ancre(chemin_cible, ancre, erreurs, origine):
    for titre in titres(chemin_cible):
        if ancre_github(titre) == ancre:
            return ancre_portail(titre)
    erreurs.append(f"{origine} : ancre #{ancre} introuvable dans {chemin_cible}")
    return ancre


def slug_portail(rel_doc, domaine):
    """doc/admin/README.md -> /doc/shinken/admin/index"""
    base = rel_doc[:-3]
    if os.path.basename(base) == "README":
        base = os.path.join(os.path.dirname(base), "index")
    return f"/doc/{domaine}/{base}".replace(os.sep, "/").replace("//", "/")


def exporte(rel_doc):
    premier = rel_doc.split(os.sep, 1)[0]
    return premier not in EXCLUS


def reecrire_liens(texte, rel_doc, domaine, erreurs):
    dossier = os.path.dirname(os.path.join(DOC, rel_doc))

    def remplace(m):
        libelle, cible = m.group(1), m.group(2)
        if re.match(r"^[a-z]+:", cible):
            return m.group(0)
        chemin, _, ancre = cible.partition("#")
        if not chemin:                                   # ancre de la même page
            nouvelle = convertir_ancre(os.path.join(DOC, rel_doc), ancre, erreurs, rel_doc)
            return f"[{libelle}](#{nouvelle})"
        absolu = os.path.normpath(os.path.join(dossier, chemin))
        rel_depot = os.path.relpath(absolu, ROOT)
        rel_cible = os.path.relpath(absolu, DOC)
        if (not rel_cible.startswith("..") and absolu.endswith(".md")
                and exporte(rel_cible) and os.path.exists(absolu)):
            adresse = slug_portail(rel_cible, domaine)
            if ancre:
                adresse += "#" + convertir_ancre(absolu, ancre, erreurs, rel_doc)
            return f"[{libelle}]({adresse})"
        if not os.path.exists(absolu):
            erreurs.append(f"{rel_doc} : cible inexistante {cible}")
        genre = "tree/" if os.path.isdir(absolu) else "blob/"
        adresse = GITHUB.replace("blob/", genre) + rel_depot.replace(os.sep, "/")
        return f"[{libelle}]({adresse}{'#' + ancre if ancre else ''})"

    morceaux = re.split(r"(```.*?```|`[^`\n]*`)", texte, flags=re.S)
    for i in range(0, len(morceaux), 2):                 # hors blocs de code
        morceaux[i] = _LIEN.sub(remplace, morceaux[i])
    return "".join(morceaux)


def _texte_brut(bloc):
    texte = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", bloc)
    texte = re.sub(r"[`*]", "", texte)
    return " ".join(texte.split())


def resume(corps):
    """Première phrase utile : suite du paragraphe « Public : », sinon premier
    paragraphe de texte. Coupée proprement à la fin d'une phrase si possible."""
    for bloc in re.split(r"\n\s*\n", corps):
        bloc = bloc.strip()
        if (not bloc or bloc.startswith(("#", ">", "|", "```", "-", "*", "1."))) \
                and not bloc.startswith("**Public"):
            continue
        if bloc.startswith("**Public"):
            reste = re.split(r"(?<=\.)\s", _texte_brut(bloc), maxsplit=1)
            if len(reste) < 2:
                continue
            texte = reste[1]
        else:
            texte = _texte_brut(bloc)
        if texte.endswith(":"):
            continue
        if len(texte) <= 220:
            return texte
        coupe = texte[:220]
        fin = coupe.rfind(". ")
        return coupe[:fin + 1] if fin > 80 else coupe.rsplit(" ", 1)[0] + "…"
    return ""


def yaml_texte(valeur):
    return '"' + str(valeur).replace("\\", "\\\\").replace('"', '\\"') + '"'


def front_matter(rel_doc, corps, titre):
    dossier = os.path.dirname(rel_doc)
    libelle, niveau, _ = DOSSIERS.get(dossier, DOSSIERS[""])
    nom = os.path.basename(rel_doc)
    niveau = NIVEAUX_PAR_FICHIER.get(nom, niveau)
    num = re.match(r"(\d+)-", nom)
    if dossier == "admin" and num:
        n = int(num.group(1))
        niveau = "debutant" if n < 5 else "intermediaire" if n < 20 else "avance"
    if nom == "README.md":
        ordre = 1
    elif num:
        ordre = int(num.group(1)) + 2
    else:
        ordre = 100
    type_ = "reference" if dossier == "admin/reference" or nom == "glossaire.md" else "guide"
    lignes = [
        "---",
        f"title: {yaml_texte(titre)}",
        f"domain: {yaml_texte(libelle)}",
        f"type: {yaml_texte(type_)}",
        f"level: {yaml_texte(niveau)}",
        'version: "1.0"',
        f'updated: "{datetime.date.today().isoformat()}"',
        'owner: "Administration Supervision"',
        'status: "review"',
        f"order: {ordre}",
        f"summary: {yaml_texte(resume(corps))}",
        "---",
        "",
    ]
    return "\n".join(lignes)


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("docs", help="dossier docs/ du portail")
    p.add_argument("--domaine", default="shinken")
    args = p.parse_args()

    cible = os.path.join(args.docs, args.domaine)
    if os.path.isdir(cible):
        shutil.rmtree(cible)
    erreurs, nombre = [], 0

    for racine, dossiers, fichiers in os.walk(DOC):
        rel_racine = os.path.relpath(racine, DOC)
        rel_racine = "" if rel_racine == "." else rel_racine
        dossiers[:] = sorted(d for d in dossiers
                             if exporte(os.path.join(rel_racine, d)) and not d.startswith("__"))
        if rel_racine in DOSSIERS:
            os.makedirs(os.path.join(cible, rel_racine), exist_ok=True)
            meta = DOSSIERS[rel_racine][2]
            with open(os.path.join(cible, rel_racine, "_domain.yml"), "w", encoding="utf-8") as f:
                for cle in ("title", "description", "icon", "order"):
                    v = meta[cle]
                    f.write(f"{cle}: {v if isinstance(v, int) else yaml_texte(v)}\n")
        for nom in sorted(fichiers):
            if not nom.endswith(".md"):
                continue
            rel_doc = os.path.join(rel_racine, nom)
            with open(os.path.join(DOC, rel_doc), encoding="utf-8") as f:
                texte = f.read()
            if texte.startswith("---\n"):                # ancien front matter
                texte = texte.split("\n---\n", 1)[1].lstrip("\n")
            m = re.search(r"^#\s+(.+)$", texte, re.M)
            titre = m.group(1).strip() if m else nom[:-3]
            corps = reecrire_liens(texte, rel_doc, args.domaine, erreurs)
            sortie = os.path.join(cible, rel_racine,
                                  "index.md" if nom == "README.md" else nom)
            os.makedirs(os.path.dirname(sortie), exist_ok=True)
            with open(sortie, "w", encoding="utf-8") as f:
                f.write(front_matter(rel_doc, texte, titre) + corps)
            nombre += 1

    print(f"{nombre} fiches exportées dans {cible}")
    for e in erreurs:
        print("  ⚠", e)
    return 1 if erreurs else 0


if __name__ == "__main__":
    sys.exit(main())
