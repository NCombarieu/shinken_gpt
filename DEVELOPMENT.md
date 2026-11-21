# Développement

Guide pour modifier le code de Shinken, le tester et proposer une
contribution. L'architecture est décrite dans
[doc/dev/architecture.md](doc/dev/architecture.md).

## Prérequis

- Python 3.11, 3.12 ou 3.13 ;
- Linux ;
- `git` ; `podman` pour construire et tester l'image ;
- `libcurl` et ses en-têtes si `pycurl` doit être compilé
  (`libcurl4-openssl-dev` sous Debian).

## Installation de développement

```bash
git clone <url-du-depot> shinken
cd shinken
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"      # paquet en mode éditable + pytest, ruff, build…
shinken-arbiter --version
```

## Organisation du dépôt

```
shinken/               cœur : daemons, objets de configuration, réseau, scheduler
  daemons/             une classe par daemon (*daemon.py)
  objects/             objets de configuration (Host, Service, Config…)
modules/               modules chargés par les daemons (livestatus, retention_pickle, named_pipe…)
bin/                   points d'entrée shinken-<daemon>, shinken-healthcheck
libexec/               scripts fournis ($PLUGINSDIR$) : notify_by_email.py…
etc/                   configuration d'exemple
test/                  tests (pytest) et leurs configurations (test/etc/)
integration/           tests d'intégration (pile Podman, essai de bout en bout)
containers/            point d'entrée de l'image
deploy/                quadlets Podman
doc/                   documentation (doc/tools/ : outils de la documentation)
```

## Tests

Commande utilisée par la CI :

```bash
python -m pytest -q test
```

Un fichier précis : `python -m pytest -q test/test_macroresolver.py`. Les
tests anciens utilisent l'API `unittest` et des configurations de
`test/etc/` ; `test/conftest.py` fournit la compatibilité. Tout correctif
s'accompagne d'un test qui échoue sans lui.

Vérifier la configuration d'exemple :

```bash
rm -rf /tmp/shinken-etc && cp -a etc /tmp/shinken-etc
sed -i -e "s#^modules_dir=.*#modules_dir=$PWD/modules#" \
       -E -e "s#^(lock_file|local_log|workdir|pack_distribution_file)=.*#\1=/tmp/shinken-etc/run.tmp#" \
       /tmp/shinken-etc/shinken.cfg
python bin/shinken-arbiter -v -c /tmp/shinken-etc/shinken.cfg
```

Tests d'intégration :

- `bash integration/podman-lab.sh` : construit l'image et démarre les six
  daemons en conteneurs, avec de vrais checks ;
- `python3 integration/e2e_smoke.py` : six daemons hors conteneur ;
  configuration, checks, Livestatus, notification SMTP, `nagios.cmd`,
  rétention.

## Qualité du code

```bash
python -m compileall -q shinken bin modules libexec integration test
ruff check shinken bin modules libexec integration test
```

La CI (`.github/workflows/ci.yml`) exécute la compilation sur Python 3.11 à
3.13, ruff, la suite de tests, la construction du paquet (`python -m build`,
`twine check`), la construction de l'image et le laboratoire Podman.

## Conventions

- **Code, docstrings, messages de commit : en anglais.** Documentation et
  commentaires de la configuration d'exemple : en français.
- Messages de commit au format conventionnel :
  `fix(scheduler): restore retention before first check`,
  `feat(modules): …`, `docs(admin): …`, `test: …`.
- Commits atomiques ; un correctif = son test.
- Style : ruff (`pyproject.toml`), lignes de 100 caractères, regex en
  chaînes brutes `r"…"`.
- Sécurité : jamais de `pickle.loads` sur une donnée reçue (utiliser
  `shinken.safepickle.SafeUnpickler`), jamais de secret dans le dépôt ni
  dans les journaux.
- Aucune donnée réelle dans les exemples : `example.com`, adresses de
  documentation `192.0.2.0/24`, `198.51.100.0/24`.
- Documentation : Markdown compatible GitHub (pas de syntaxe MkDocs),
  liens relatifs vérifiés par `python doc/tools/check_links.py`. Les pages
  de référence se régénèrent avec `python doc/tools/gen_reference.py`
  après toute modification des `properties` des objets ou des commandes
  externes.
- Toute évolution visible des utilisateurs est ajoutée au `Changelog`.

## Proposer une modification

1. Créer une branche depuis `modernize/podman-python3`.
2. Coder, tester (`python -m pytest -q test`), mettre à jour la doc.
3. Ouvrir une *pull request* décrivant le problème, la solution et la façon
   de tester. La CI doit être verte.

Voir aussi [CONTRIBUTING.rst](CONTRIBUTING.rst).
