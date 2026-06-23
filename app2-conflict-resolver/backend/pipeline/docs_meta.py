"""Curated metadata for the corpus, keyed by PDF filename.

Data, deliberately kept apart from extraction logic. Documents absent from this
registry are still extracted — the filename stem becomes the fallback id — so
dropping a new PDF into a cluster subfolder is enough to include it.

Each PDF's cluster is its parent subfolder (``documents/<cluster>/<file>.pdf``);
pairwise analysis only ever compares documents within the same cluster.
"""

DOCS_META: dict[str, dict] = {
    # ── Lighting cluster ───────────────────────────────────────────────────────
    "ITM-CL-55.2.pdf": {
        "id": "ITM-CL-55.2",
        "title": "ITM-CL 55.2 – Éclairage des lieux de travail",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1997-10-16",
        "scope": "Prescriptions de sécurité et de santé types pour l'éclairage de tous les lieux de travail au Luxembourg",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-CL-55-2.pdf",
    },
    "ITM-ET-32.10.pdf": {
        "id": "ITM-ET-32.10",
        "title": "ITM-ET 32.10 – Protection des Travailleurs (Art. 15 Éclairage)",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1997-10-16",
        "scope": "Prescriptions générales de sécurité, de santé et d'hygiène pour les entreprises industrielles, commerciales et tertiaires",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-ET-32-10.pdf",
    },
    "ITM-CL-144.1.pdf": {
        "id": "ITM-CL-144.1",
        "title": "ITM-CL 144.1 – Installations électriques de chantier (Art. 7 Éclairage)",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "2004-07-15",
        "scope": "Prescriptions de sécurité types pour les installations électriques provisoires sur chantiers de construction",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-101-200/ITM-CL-144-1.pdf",
    },
    # ── Ventilation cluster ────────────────────────────────────────────────────
    "ITM-CL-53.1.pdf": {
        "id": "ITM-CL-53.1",
        "title": "ITM-CL 53.1 – Installations de ventilation et de conditionnement d'air",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1996-10-14",
        "scope": "Prescriptions de sécurité types pour les installations de ventilation, d'aération et de conditionnement d'air sur les lieux de travail",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-CL-53-1.pdf",
    },
    "ITM-CL-62.1.pdf": {
        "id": "ITM-CL-62.1",
        "title": "ITM-CL 62.1 – Ventilation, aération, chauffage et atmosphère des lieux de travail (petits ateliers)",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1991-10-14",
        "scope": "Prescriptions de sécurité et de santé types pour la ventilation, l'aération, le chauffage et l'atmosphère dans les petits ateliers",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-CL-62-1.pdf",
    },
    "ITM-CL-86.1.pdf": {
        "id": "ITM-CL-86.1",
        "title": "ITM-CL 86.1 – Contrôle de l'atmosphère sur les lieux de travail",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1995-04-07",
        "scope": "Prescriptions générales de surveillance de l'atmosphère sur les lieux de travail susceptibles d'être contaminés par des substances dangereuses",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-CL-86-1.pdf",
    },
    # ── Ascenseurs cluster ─────────────────────────────────────────────────────
    "ITM-CL-82.1.pdf": {
        "id": "ITM-CL-82.1",
        "title": "ITM-CL 82.1 – Mise en sécurité des ascenseurs mus électriquement",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1995-03-21",
        "scope": "Prescriptions de sécurité types pour la mise en conformité et l'exploitation des ascenseurs à traction électrique",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-CL-82-1.pdf",
    },
    "ITM-CL-83.1.pdf": {
        "id": "ITM-CL-83.1",
        "title": "ITM-CL 83.1 – Mise en sécurité des ascenseurs mus hydrauliquement",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "1994-03-21",
        "scope": "Prescriptions de sécurité types pour la mise en conformité et l'exploitation des ascenseurs hydrauliques",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-1-100/ITM-CL-82-1.pdf",
    },
    "ITM-CL-230.2.pdf": {
        "id": "ITM-CL-230.2",
        "title": "ITM-CL 230.2 – Ascenseurs (directive 95/16/CE)",
        "authority": "Inspection du Travail et des Mines (ITM)",
        "date": "2000-08-02",
        "scope": "Prescriptions de sécurité types pour les ascenseurs régis par la directive européenne 95/16/CE",
        "url": "https://itm.public.lu/dam-assets/fr/securite-sante/conditions-types/itm-cl-201-300/ITM-CL-230-2.pdf",
    },
}
