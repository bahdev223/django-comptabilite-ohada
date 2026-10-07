#!/usr/bin/env python3
"""Real TCP HTTP journey against an isolated disposable SQLite database.

Run with either supported interpreter, optionally with --restricted. No existing
DB or integration credentials are read or changed. GitHub Actions is not used.
"""
import argparse
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--restricted", action="store_true")
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="ohada-http-") as temporary:
        temp = Path(temporary)
        settings_file = temp / "ohada_http_settings.py"
        settings_file.write_text(
            "from standalone.settings import *\n"
            "COMPTABILITE_OHADA = {**COMPTABILITE_OHADA, 'DEVISE_PAR_DEFAUT': 'XOF'}\n"
            + ("ROOT_URLCONF = 'comptabilite_ohada.integration_urls'\n" if args.restricted else ""),
            encoding="utf-8",
        )
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "ohada_http_settings",
               "DB_ENGINE": "django.db.backends.sqlite3", "DB_NAME": str(temp / "http.sqlite3"),
               "COMPTES_INTEGRATION_ENABLED": "0", "DJANGO_ALLOWED_HOSTS": "127.0.0.1",
               "PYTHONPATH": os.pathsep.join((str(temp), str(repo)))}
        subprocess.run([sys.executable, "-m", "django", "migrate", "--noinput", "--verbosity", "0"],
                       env=env, cwd=repo, check=True)
        os.environ.update({key: env[key] for key in (
            "DJANGO_SETTINGS_MODULE", "DB_ENGINE", "DB_NAME", "COMPTES_INTEGRATION_ENABLED",
            "DJANGO_ALLOWED_HOSTS",
        )})
        sys.path[:0] = [str(temp), str(repo)]
        import django
        django.setup()
        from comptabilite_ohada.models import (
            ApplicationClienteComptable, CompteComptable, ConfigurationComptable,
            EcritureComptable, EvenementMetier, ExerciceComptable, JournalComptable,
            OrganisationComptable, RegleEvenementComptable,
        )
        from comptabilite_ohada.services.exercice_service import ValidationService
        keys = {}
        clients = {}
        for tenant in ("ALPHA", "BETA"):
            org = OrganisationComptable.objects.create(code=tenant, nom=tenant)
            clients[tenant], keys[tenant] = ApplicationClienteComptable.generer_cle(
                org, "http-verification", ["accounting.read", "accounting.events.write"]
            )
            ConfigurationComptable.objects.create(entreprise_id=tenant, devise="XOF")
            ExerciceComptable.objects.create(entreprise_id=tenant, code="2026",
                                             date_debut="2026-01-01", date_fin="2026-12-31")
            JournalComptable.objects.create(entreprise_id=tenant, code="OD", libelle="OD", type_journal="OD")
            for code, nature in (("658", "CHARGE"), ("571", "ACTIF")):
                CompteComptable.objects.create(entreprise_id=tenant, code=code, libelle=code,
                                               nature=nature, sens="DEBIT")
            RegleEvenementComptable.objects.create(entreprise_id=tenant,
                type_evenement="project.expense.created", code_regle="ECRITURE_GENERIQUE")
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        def call(path, tenant="ALPHA", payload=None, key=None, expected=200, headers=None):
            req = Request(base + path, data=json.dumps(payload).encode() if payload is not None else None,
                          headers={"X-API-Key": keys[tenant] if key is None else key,
                                   "Content-Type": "application/json", **(headers or {})})
            try:
                response = urlopen(req, timeout=10)
            except HTTPError as exc:
                response = exc
            with response:
                status = response.code
                body = response.read()
            assert status == expected, (path, status, expected, body.decode()[:500])
            return json.loads(body) if body and body.startswith((b"{", b"[")) else None

        def event(amount, key="same-key"):
            return {"type_evenement": "project.expense.created", "source_system": "saheltech-platform",
                    "source_type": "project", "source_id": key, "idempotency_key": key,
                    "payload": {"date": "2026-10-03", "libelle": "HTTP project cost", "journal_code": "OD",
                                "source_reference": "SAME", "dimensions": {"PROJECT": "SAME", "PHASE": "PH1"},
                                "lignes": [{"compte": "658", "debit": amount, "dimensions": {"PROJECT": "SAME"}},
                                           {"compte": "571", "credit": amount}]}}

        with (temp / "server.log").open("w") as log:
            server = subprocess.Popen([sys.executable, "-m", "django", "runserver", f"127.0.0.1:{port}",
                                       "--noreload"], env=env, cwd=repo, stdout=log, stderr=log)
            try:
                deadline = time.monotonic() + 15
                while True:
                    try:
                        call("/api/v1/analytics/costs/?PROJECT=SAME")
                        break
                    except URLError:
                        if server.poll() is not None or time.monotonic() > deadline:
                            raise RuntimeError((temp / "server.log").read_text())
                        time.sleep(0.1)
                first = call("/api/v1/events/", payload=event("125.00"), expected=201)
                beta = call("/api/v1/events/", tenant="BETA", payload=event("80.00"), expected=201)
                assert first["status"] == beta["status"] == "recorded"
                assert first["entry_id"] != beta["entry_id"]
                replay = call("/api/v1/events/", payload=event("125.00"))
                assert replay["entry_id"] == first["entry_id"]
                raced = event("7.00", "http-race")
                raced["payload"]["source_reference"] = "RACE"
                raced["payload"]["dimensions"]["PROJECT"] = "RACE"
                raced["payload"]["lignes"][0]["dimensions"]["PROJECT"] = "RACE"

                def post_race(_):
                    req = Request(base + "/api/v1/events/", data=json.dumps(raced).encode(),
                                  headers={"X-API-Key": keys["ALPHA"], "Content-Type": "application/json"})
                    with urlopen(req, timeout=10) as response:
                        return response.code, json.loads(response.read())

                with ThreadPoolExecutor(max_workers=2) as pool:
                    race_results = list(pool.map(post_race, range(2)))
                assert sorted(code for code, _ in race_results) == [200, 201]
                assert race_results[0][1]["entry_id"] == race_results[1][1]["entry_id"]
                changed = event("126.00")
                call("/api/v1/events/", payload=changed, expected=409)
                alpha_cost = call("/api/v1/analytics/costs/?PROJECT=SAME&PHASE=PH1")
                assert alpha_cost["total_cost"] == "125.00" and alpha_cost["currency"] == "XOF"
                assert call("/api/v1/analytics/costs/?PROJECT=SAME", tenant="BETA")["total_cost"] == "80.00"
                assert call("/api/v1/analytics/costs/?PROJECT=ABSENT")["total_cost"] == "0.00"
                call("/api/v1/analytics/costs/?PROJECT=SAME", key="invalid", expected=401)
                forged = deepcopy(event("12.00", "forged"))
                forged["payload"]["lignes"][0]["dimensions"]["PROJECT"] = "OTHER"
                call("/api/v1/events/", payload=forged, expected=422)
                injected = call("/api/v1/analytics/costs/?PROJECT=SAME", headers={"X-Enterprise-ID": "BETA"})
                assert injected["total_cost"] == "125.00"
                clients["ALPHA"].scopes = ["accounting.read"]
                clients["ALPHA"].save(update_fields=["scopes"])
                call("/api/v1/events/", payload=event("3.00", "read-only"), expected=403)
                clients["ALPHA"].scopes = ["accounting.read", "accounting.events.write"]
                clients["ALPHA"].save(update_fields=["scopes"])
                original = EcritureComptable.objects.get(pk=first["entry_id"])
                ValidationService.annuler_ecriture(original, raison="HTTP verification")
                assert call("/api/v1/analytics/costs/?PROJECT=SAME")["total_cost"] == "0.00"
                assert call("/api/v1/analytics/costs/?PROJECT=SAME", tenant="BETA")["total_cost"] == "80.00"
                ExerciceComptable.objects.filter(entreprise_id="ALPHA").update(cloture=True)
                JournalComptable.objects.filter(entreprise_id="ALPHA").update(actif=False)
                assert call("/api/v1/events/", payload=event("125.00"))["entry_id"] == first["entry_id"]
                clients["ALPHA"].actif = False
                clients["ALPHA"].save(update_fields=["actif"])
                call("/api/v1/analytics/costs/?PROJECT=SAME", expected=401)
                if args.restricted:
                    for path in ("/api/v1/comptes/", "/api/v1/regles-evenements/", "/api/comptabilite/comptes/"):
                        call(path, tenant="BETA", expected=404)
                assert EcritureComptable.objects.count() == 4
                assert EvenementMetier.objects.count() == 4  # three recorded + one audited error
                print(json.dumps({"python": sys.version.split()[0], "host": "restricted" if args.restricted else "canonical",
                                  "result": "PASS", "alpha_before_reversal": "125.00", "alpha_after_reversal": "0.00",
                                  "beta": "80.00", "currency": "XOF", "entries": 4, "receipts": 4,
                                  "concurrent_replay": "PASS"}))
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait()


if __name__ == "__main__":
    main()
