"""
Zone rules derived from RGD 28 juillet 2011 (Luxembourg PAG regulations).
Each zone maps to: allowed uses, height limits, required documents, and SECO touchpoints.
"""

ZONE_RULES: dict[str, dict] = {
    "HAB_1": {
        "name": "Zone d'habitation 1",
        "density": "Faible densité",
        "description": "Zone résidentielle à faible densité. Destinée aux maisons unifamiliales et bifamiliales avec jardins privatifs.",
        "allowed_uses": [
            "Maisons unifamiliales",
            "Maisons bifamiliales",
            "Équipements de quartier intégrés (crèche, petite école)",
        ],
        "forbidden_uses": [
            "Logements collectifs (immeubles)",
            "Commerce",
            "Industrie ou artisanat",
        ],
        "height": {
            "max_floors": 2,
            "combles": True,
            "label": "2 niveaux + combles",
        },
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zones HAB (Art. 5-12)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "PAG communal – règlement des zones HAB_1",
                "url": "https://geoportail.lu/",
                "type": "communal",
                "note": "Télécharger via le géoportail national, chercher la commune concernée",
            },
        ],
        "seco_touchpoints": [
            "Contrôle technique de construction (CTC)",
            "Vérification de la stabilité structurelle",
            "Bilan énergétique (label énergétique requis)",
        ],
        "checklist": [
            "Vérifier le CUS/COS communal applicable",
            "Confirmer la distance aux limites de propriété (recul)",
            "Vérifier l'absence de servitudes (cours d'eau, lignes HT)",
            "Contrôler la faisabilité raccordement réseaux (eau, assainissement)",
        ],
        "color": "#fde68a",
    },
    "HAB_2": {
        "name": "Zone d'habitation 2",
        "density": "Densité moyenne",
        "description": "Zone résidentielle de densité moyenne. Permet les immeubles collectifs. Rez + 3 à 5 niveaux selon la commune.",
        "allowed_uses": [
            "Immeubles à appartements",
            "Maisons plurifamiliales",
            "Résidences pour personnes âgées",
            "Équipements de quartier",
        ],
        "forbidden_uses": [
            "Industrie lourde",
            "Entrepôts logistiques",
        ],
        "height": {
            "max_floors": 5,
            "combles": True,
            "label": "Rez + 4 niveaux + combles (variable par commune)",
        },
        "pap_required": True,
        "pap_type": "PAP-NQ ou PAP-QE selon secteur",
        "documents": [
            {
                "title": "RGD 2011 – Zones HAB (Art. 5-12)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "PAG communal – règlement des zones HAB_2",
                "url": "https://geoportail.lu/",
                "type": "communal",
            },
            {
                "title": "Loi 2004 sur l'aménagement du territoire",
                "url": "http://data.legilux.public.lu/eli/etat/leg/loi/2004/06/21/n1/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": [
            "Contrôle technique de construction (CTC)",
            "Contrôle incendie (ERP si >50 logements)",
            "Accessibilité PMR obligatoire",
            "Bilan énergétique + certification",
            "Contrôle ascenseur(s)",
        ],
        "checklist": [
            "Vérifier si PAP approuvé ou à initier",
            "Confirmer gabarit maximal (CUS, hauteur, retraits)",
            "Étude de mobilité si >20 logements",
            "Plan de gestion des eaux pluviales",
            "Accessibilité PMR (cheminements, ascenseurs, sanitaires)",
        ],
        "color": "#fbbf24",
    },
    "MIX_u": {
        "name": "Zone mixte urbaine",
        "density": "Haute densité",
        "description": "Zone urbaine à fort coefficient. Usage mixte : commercial au rez-de-chaussée, résidentiel ou bureaux aux étages. Typique des centres-villes.",
        "allowed_uses": [
            "Commerce de détail (rez-de-chaussée)",
            "Bureaux",
            "Logements (étages)",
            "Hôtels",
            "Équipements collectifs",
        ],
        "forbidden_uses": [
            "Industrie lourde",
            "Entrepôts",
            "Maisons unifamiliales isolées",
        ],
        "height": {
            "max_floors": 7,
            "combles": False,
            "label": "Variable (Rez + 4 à 7 selon commune), souvent alignement à la rue",
        },
        "pap_required": True,
        "pap_type": "PAP-NQ (nouveaux quartiers) ou PAP-QE (quartiers existants)",
        "documents": [
            {
                "title": "RGD 2011 – Zones MIX (Art. 13-18)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "PAG communal – règlement MIX_u",
                "url": "https://geoportail.lu/",
                "type": "communal",
            },
            {
                "title": "Règlement grand-ducal sur la sécurité incendie des ERP",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2012/03/06/n1/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": [
            "Contrôle technique de construction (CTC) obligatoire",
            "Sécurité incendie ERP (Établissement Recevant du Public)",
            "Accessibilité PMR complète",
            "Contrôle des installations techniques (sprinklers, désenfumage)",
            "Certification énergétique",
        ],
        "checklist": [
            "PAP approuvé ? (sinon procédure d'approbation à lancer)",
            "Vérifier programme obligatoire RDC commercial (certaines communes)",
            "Plan d'évacuation incendie dès conception",
            "Étude de stationnement (nombre de places PMR, vélos)",
            "Intégration des prescriptions architecturales du PAP",
        ],
        "color": "#f97316",
    },
    "MIX_v": {
        "name": "Zone mixte villageoise",
        "density": "Densité modérée",
        "description": "Zone caractéristique des villages luxembourgeois. Mélange habitat, petit commerce et artisanat en préservant le tissu villageois traditionnel.",
        "allowed_uses": [
            "Habitations (uni- et plurifamiliales)",
            "Petit commerce",
            "Artisanat non nuisant",
            "Équipements communautaires",
        ],
        "forbidden_uses": [
            "Industrie",
            "Grandes surfaces commerciales",
            "Entrepôts",
        ],
        "height": {
            "max_floors": 3,
            "combles": True,
            "label": "Rez + 2 niveaux + combles, toiture à double pente souvent exigée",
        },
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zones MIX (Art. 13-18)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "PAG communal – prescriptions architecturales village",
                "url": "https://geoportail.lu/",
                "type": "communal",
            },
        ],
        "seco_touchpoints": [
            "Contrôle technique (CTC) si surface >300m²",
            "Vérification conformité prescriptions architecturales",
        ],
        "checklist": [
            "Vérifier prescriptions de gabarit et matériaux (toiture, façade)",
            "Distance aux limites de parcelle selon règlement communal",
            "Raccordement aux réseaux existants du village",
        ],
        "color": "#fb923c",
    },
    "MIX_r": {
        "name": "Zone mixte rurale",
        "density": "Faible densité",
        "description": "Zone rurale à usage mixte : habitat, agriculture, activités non nuisantes. Très restrictive sur les nouvelles constructions.",
        "allowed_uses": [
            "Habitations rurales existantes (extension limitée)",
            "Bâtiments agricoles",
            "Artisanat lié à l'agriculture",
        ],
        "forbidden_uses": [
            "Nouvelles maisons isolées (en général)",
            "Commerce",
            "Industrie",
        ],
        "height": {
            "max_floors": 2,
            "combles": True,
            "label": "Limité, conforme au bâti existant",
        },
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zones MIX (Art. 13-18)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": [
            "Vérification conformité usage agricole",
        ],
        "checklist": [
            "Confirmer que le projet est une extension et non une nouvelle construction",
            "Vérifier dérogations possibles via commune",
        ],
        "color": "#fdba74",
    },
    "MIX_c": {
        "name": "Zone mixte centrale",
        "density": "Très haute densité",
        "description": "Zone de centre-ville dense. Priorité au commerce et aux services au rez-de-chaussée. Logements et bureaux aux étages.",
        "allowed_uses": [
            "Commerce (obligatoire en RDC dans certaines communes)",
            "Bureaux, services",
            "Hôtels, restaurants",
            "Logements (étages)",
        ],
        "forbidden_uses": ["Industrie", "Entrepôts", "Habitat exclusif en RDC"],
        "height": {
            "max_floors": 8,
            "combles": False,
            "label": "Variable, souvent alignement obligatoire à la rue",
        },
        "pap_required": True,
        "pap_type": "PAP-QE obligatoire",
        "documents": [
            {
                "title": "RGD 2011 – Zones MIX (Art. 13-18)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "RGD Sécurité incendie ERP",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2012/03/06/n1/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": [
            "CTC obligatoire",
            "Sécurité incendie ERP",
            "Accessibilité PMR complète",
            "Contrôle installations techniques",
        ],
        "checklist": [
            "PAP-QE approuvé ou procédure à engager",
            "Étude de mobilité",
            "Plan de gestion des livraisons",
        ],
        "color": "#ef4444",
    },
    "FOR": {
        "name": "Zone forestière",
        "density": "Non constructible",
        "description": "Forêts protégées par la loi forestière luxembourgeoise. Constructibilité exclue sauf équipements strictement liés à la sylviculture.",
        "allowed_uses": [
            "Exploitation forestière",
            "Abris forestiers légers (avec autorisation)",
        ],
        "forbidden_uses": [
            "Toute construction permanente",
            "Défrichement sans autorisation ministérielle",
            "Usage résidentiel ou commercial",
        ],
        "height": {"max_floors": 0, "label": "Non constructible"},
        "pap_required": False,
        "documents": [
            {
                "title": "Loi du 19 janvier 2004 concernant la protection de la nature",
                "url": "http://data.legilux.public.lu/eli/etat/leg/loi/2004/01/19/n1/jo",
                "type": "regulation",
            },
            {
                "title": "Loi forestière modifiée",
                "url": "https://legilux.public.lu/eli/etat/leg/loi/2018/07/17/a621/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": [],
        "checklist": [
            "STOP – zone non constructible",
            "Tout projet nécessite une dérogation ministérielle",
            "Vérifier si erreur de classement (recours possible)",
        ],
        "color": "#16a34a",
    },
    "AGR": {
        "name": "Zone agricole",
        "density": "Non constructible (hors usage agricole)",
        "description": "Zone réservée à l'exploitation agricole. Les constructions sont limitées aux bâtiments d'exploitation agricole strictement nécessaires.",
        "allowed_uses": [
            "Bâtiments d'exploitation agricole (étables, hangars)",
            "Serres de production",
        ],
        "forbidden_uses": [
            "Habitat",
            "Commerce",
            "Industrie",
            "Loisirs",
        ],
        "height": {"max_floors": 0, "label": "Bâtiments agricoles uniquement"},
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zone AGR",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "Loi agricole – autorisation de construire en zone verte",
                "url": "http://data.legilux.public.lu/eli/etat/leg/loi/1999/08/18/n2/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": ["Contrôle si bâtiment agricole > 300m²"],
        "checklist": [
            "Vérifier que le demandeur est bien exploitant agricole",
            "L'usage agricole doit être démontré",
            "Autorisation du Ministre de l'Agriculture requise",
        ],
        "color": "#86efac",
    },
    "BEP": {
        "name": "Zone de bâtiments et équipements publics",
        "density": "Variable",
        "description": "Réservée aux équipements d'intérêt général : écoles, hôpitaux, administrations, infrastructures publiques.",
        "allowed_uses": [
            "Équipements scolaires",
            "Équipements sanitaires et sociaux",
            "Administrations publiques",
            "Infrastructures de transport",
            "Équipements sportifs et culturels",
        ],
        "forbidden_uses": [
            "Habitat privé",
            "Commerce privé",
            "Industrie",
        ],
        "height": {"max_floors": 4, "label": "Variable selon programme"},
        "pap_required": True,
        "pap_type": "PAP spécial ou dérogation communale",
        "documents": [
            {
                "title": "RGD 2011 – Zone BEP",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "RGD Sécurité incendie ERP (établissements recevant du public)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2012/03/06/n1/jo",
                "type": "regulation",
            },
            {
                "title": "Norme PMR – accessibilité des bâtiments publics",
                "url": "https://gouvernement.lu/fr/dossiers/2018/accessibilite.html",
                "type": "norm",
            },
        ],
        "seco_touchpoints": [
            "CTC systématique",
            "Sécurité incendie ERP obligatoire",
            "Accessibilité PMR intégrale",
            "Contrôle installations spécifiques (cuisine collective, piscine, etc.)",
        ],
        "checklist": [
            "Maître d'ouvrage public identifié ?",
            "Programme validé par la tutelle (Ministère concerné)",
            "Étude d'accessibilité PMR dès avant-projet",
            "Coordination sécurité incendie intégrée à la conception",
        ],
        "color": "#60a5fa",
    },
    "VERD": {
        "name": "Zone de verdure",
        "density": "Non constructible",
        "description": "Espaces verts de liaison entre zones urbanisées. Rôle écologique et paysager. Constructibilité très limitée.",
        "allowed_uses": ["Aménagements paysagers légers", "Cheminements piétons/vélos"],
        "forbidden_uses": ["Constructions permanentes", "Parking"],
        "height": {"max_floors": 0, "label": "Non constructible"},
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zones vertes",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": [],
        "checklist": ["Zone non constructible – projet incompatible sauf aménagement paysager"],
        "color": "#a7f3d0",
    },
    "JAR": {
        "name": "Zone de jardins",
        "density": "Non constructible",
        "description": "Jardins privatifs associés à des habitations. Aucune construction neuve.",
        "allowed_uses": ["Jardins privatifs", "Abris de jardin légers (< 6m² selon commune)"],
        "forbidden_uses": ["Constructions permanentes", "Logements supplémentaires"],
        "height": {"max_floors": 0, "label": "Non constructible"},
        "pap_required": False,
        "documents": [
            {
                "title": "PAG communal – zone de jardins",
                "url": "https://geoportail.lu/",
                "type": "communal",
            }
        ],
        "seco_touchpoints": [],
        "checklist": ["Non constructible – vérifier si requalification possible en HAB"],
        "color": "#6ee7b7",
    },
    "PARC": {
        "name": "Zone de parcs",
        "density": "Non constructible",
        "description": "Parcs publics ou privés à préserver. Constructibilité nulle.",
        "allowed_uses": ["Parcs et jardins publics", "Mobilier urbain léger"],
        "forbidden_uses": ["Toute construction permanente"],
        "height": {"max_floors": 0, "label": "Non constructible"},
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zones de parcs",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": [],
        "checklist": ["Non constructible"],
        "color": "#34d399",
    },
    "REC": {
        "name": "Zone de récréation",
        "density": "Constructibilité limitée",
        "description": "Zones de sport et loisirs. Constructions légères liées à l'activité récréative autorisées.",
        "allowed_uses": [
            "Équipements sportifs de plein air",
            "Vestiaires, tribunes légères",
            "Terrains de jeux",
            "Camping (si prévu par commune)",
        ],
        "forbidden_uses": ["Habitat permanent", "Commerce non lié aux loisirs"],
        "height": {"max_floors": 1, "label": "Constructions légères uniquement"},
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zone REC",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": ["Contrôle tribunes et gradins si accueil public"],
        "checklist": ["Vérifier programme autorisé par PAG communal", "ERP si accueil >50 personnes"],
        "color": "#2dd4bf",
    },
    "ECO_c1": {
        "name": "Zone d'activités économiques – Commerce et artisanat",
        "density": "Densité modérée",
        "description": "Zone destinée au commerce de détail, artisanat et PME. Exclut l'habitat.",
        "allowed_uses": [
            "Commerce de détail (< 400m² surface de vente)",
            "Artisanat",
            "PME / bureaux",
            "Restauration",
        ],
        "forbidden_uses": [
            "Habitation",
            "Industrie lourde",
            "Grandes surfaces (> 400m²)",
        ],
        "height": {"max_floors": 3, "label": "Rez + 2 niveaux"},
        "pap_required": True,
        "pap_type": "PAP-NQ ou PAP-QE",
        "documents": [
            {
                "title": "RGD 2011 – Zones ECO (Art. 19-28)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "Loi du 2 septembre 2011 sur le commerce",
                "url": "http://data.legilux.public.lu/eli/etat/leg/loi/2011/09/02/n1/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": [
            "CTC si > 300m²",
            "Sécurité incendie ERP",
            "Accessibilité PMR obligatoire",
        ],
        "checklist": [
            "Surface de vente < 400m² ? (sinon procédure grande surface)",
            "Étude de mobilité / parking",
            "Accessibilité PMR (rampes, sanitaires adaptés)",
        ],
        "color": "#c084fc",
    },
    "ECO_c2": {
        "name": "Zone d'activités économiques – Commerce (moyen)",
        "density": "Densité modérée",
        "description": "Commerce de taille moyenne. Surface de vente entre 400 et 2000m². Autorisation ministérielle requise.",
        "allowed_uses": ["Commerce moyen (400–2000m²)", "Galerie commerciale", "Restauration"],
        "forbidden_uses": ["Habitat", "Industrie"],
        "height": {"max_floors": 2, "label": "Rez + 1 niveau"},
        "pap_required": True,
        "pap_type": "PAP-NQ + autorisation commerce",
        "documents": [
            {
                "title": "RGD 2011 – Zones ECO",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "Autorisation d'établissement – Ministère de l'Économie",
                "url": "https://guichet.public.lu/fr/entreprises/creation/autorisations-etablissement.html",
                "type": "permit",
            },
        ],
        "seco_touchpoints": ["CTC obligatoire", "Sécurité incendie ERP", "PMR"],
        "checklist": [
            "Autorisation d'établissement (Ministère de l'Économie)",
            "Étude d'impact commercial",
            "Étude de trafic",
        ],
        "color": "#a855f7",
    },
    "ECO_c3": {
        "name": "Zone d'activités économiques – Grande surface",
        "density": "Basse densité",
        "description": "Grandes surfaces commerciales > 2000m². Très encadrées – procédure lourde d'autorisation.",
        "allowed_uses": ["Grande surface > 2000m²", "Centre commercial"],
        "forbidden_uses": ["Habitat", "Industrie", "Commerce alimentaire de proximité seul"],
        "height": {"max_floors": 1, "label": "Plain-pied généralement"},
        "pap_required": True,
        "pap_type": "PAP spécial + autorisation grande surface",
        "documents": [
            {
                "title": "RGD 2011 – Zone ECO_c3",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "Procédure grande surface – Ministère de l'Économie",
                "url": "https://guichet.public.lu/fr/entreprises/creation/autorisations-etablissement.html",
                "type": "permit",
            },
        ],
        "seco_touchpoints": ["CTC", "Sécurité incendie (sprinklers obligatoires)", "PMR"],
        "checklist": [
            "Autorisation grande surface (procédure spécifique)",
            "Étude d'impact sur le commerce existant",
            "Étude de mobilité et de trafic approfondie",
            "Système sprinkler obligatoire",
        ],
        "color": "#7c3aed",
    },
    "ECO_n": {
        "name": "Zone d'activités économiques – Industrie",
        "density": "Variable",
        "description": "Zone industrielle et logistique. Activités potentiellement nuisantes.",
        "allowed_uses": ["Industrie", "Logistique", "Entrepôts", "Ateliers de production"],
        "forbidden_uses": ["Habitat", "Commerce de détail", "ERP grand public"],
        "height": {"max_floors": 2, "label": "Variable selon activité"},
        "pap_required": True,
        "pap_type": "PAP-NQ industriel",
        "documents": [
            {
                "title": "RGD 2011 – Zones ECO industrie",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            },
            {
                "title": "Loi relative aux établissements classés (IPPC/SEVESO)",
                "url": "http://data.legilux.public.lu/eli/etat/leg/loi/2012/06/21/n1/jo",
                "type": "regulation",
            },
        ],
        "seco_touchpoints": [
            "CTC si > 300m²",
            "Vérification structure (charges lourdes, ponts roulants)",
            "Établissement classé : dossier IPPC si applicable",
        ],
        "checklist": [
            "Activité classée IPPC/SEVESO ? (dossier spécifique)",
            "Étude de bruit et vibrations",
            "Gestion des eaux industrielles",
            "Plan d'urgence interne si SEVESO",
        ],
        "color": "#6d28d9",
    },
    "ECO_r": {
        "name": "Zone d'activités économiques – Recherche",
        "density": "Densité modérée",
        "description": "Zone dédiée à la R&D, aux bureaux de haute technologie et à l'innovation.",
        "allowed_uses": ["R&D", "Bureaux high-tech", "Laboratoires", "Centres de formation"],
        "forbidden_uses": ["Industrie lourde", "Habitat", "Commerce généraliste"],
        "height": {"max_floors": 4, "label": "Rez + 3 niveaux"},
        "pap_required": True,
        "pap_type": "PAP-NQ recherche",
        "documents": [
            {
                "title": "RGD 2011 – Zones ECO recherche",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": ["CTC", "Contrôle laboratoires si substances dangereuses"],
        "checklist": ["Vérifier nature exacte de la R&D (risques chimiques/biologiques ?)"],
        "color": "#8b5cf6",
    },
    "COM": {
        "name": "Zone commerciale",
        "density": "Densité modérée",
        "description": "Ancienne désignation commerciale (PAG antérieurs à 2011). Assimilée à ECO_c selon commune.",
        "allowed_uses": ["Commerce", "Bureaux", "Services"],
        "forbidden_uses": ["Habitat", "Industrie lourde"],
        "height": {"max_floors": 3, "label": "Rez + 2 niveaux"},
        "pap_required": True,
        "pap_type": "PAP communal",
        "documents": [
            {
                "title": "RGD 2011 – correspondance zones anciennes",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": ["CTC", "ERP si accueil public"],
        "checklist": ["Vérifier correspondance avec zones ECO 2011", "PAG à jour ?"],
        "color": "#e879f9",
    },
    "SPEC": {
        "name": "Zone spéciale",
        "density": "Définie par commune",
        "description": "Zone à usage spécifique défini par la commune. Contenu variable – consulter le PAG et le PAP communal.",
        "allowed_uses": ["Défini par le règlement communal spécifique"],
        "forbidden_uses": ["Tout ce qui n'est pas explicitement autorisé"],
        "height": {"max_floors": None, "label": "Défini par PAG/PAP communal"},
        "pap_required": True,
        "pap_type": "PAP spécial",
        "documents": [
            {
                "title": "PAG communal – Zone spéciale concernée",
                "url": "https://geoportail.lu/",
                "type": "communal",
            }
        ],
        "seco_touchpoints": ["Variable selon programme"],
        "checklist": ["Consulter impérativement le PAG communal pour cette zone spéciale"],
        "color": "#94a3b8",
    },
    "GARE": {
        "name": "Zone de gare",
        "density": "Infrastructure",
        "description": "Infrastructure ferroviaire et abords de gare. CFL / État. Constructions liées au transport uniquement.",
        "allowed_uses": ["Infrastructures ferroviaires", "Gares", "P+R"],
        "forbidden_uses": ["Habitat privé", "Commerce non lié aux voyageurs"],
        "height": {"max_floors": None, "label": "Variable"},
        "pap_required": True,
        "pap_type": "PAP infrastructure CFL/État",
        "documents": [
            {
                "title": "Loi sur les chemins de fer",
                "url": "https://legilux.public.lu/",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": ["Coordination avec CFL obligatoire"],
        "checklist": ["Maître d'ouvrage : CFL ou État", "Coordination intermodale"],
        "color": "#475569",
    },
    "VIT": {
        "name": "Zone viticole",
        "density": "Non constructible",
        "description": "Vignes de la Moselle luxembourgeoise. Protection stricte.",
        "allowed_uses": ["Viticulture", "Caves vinicoles existantes"],
        "forbidden_uses": ["Toute nouvelle construction", "Habitat"],
        "height": {"max_floors": 0, "label": "Non constructible"},
        "pap_required": False,
        "documents": [
            {
                "title": "Loi viticole luxembourgeoise",
                "url": "https://legilux.public.lu/",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": [],
        "checklist": ["Zone protégée – non constructible"],
        "color": "#a16207",
    },
    "HOR": {
        "name": "Zone horticole",
        "density": "Non constructible",
        "description": "Production horticole (serres, pépinières). Constructions liées à l'activité uniquement.",
        "allowed_uses": ["Serres de production", "Pépinières"],
        "forbidden_uses": ["Habitat", "Commerce non lié"],
        "height": {"max_floors": 1, "label": "Serres et hangars uniquement"},
        "pap_required": False,
        "documents": [
            {
                "title": "RGD 2011 – Zone HOR",
                "url": "http://data.legilux.public.lu/eli/etat/leg/rgd/2011/07/28/n3/jo",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": [],
        "checklist": ["Activité agricole/horticole à démontrer"],
        "color": "#65a30d",
    },
    "AERO": {
        "name": "Zone aéroportuaire",
        "density": "Infrastructure",
        "description": "Emprise aéroportuaire (Luxembourg-Findel). Réglementée par l'autorité aéronautique.",
        "allowed_uses": ["Infrastructures aéronautiques", "Fret aérien", "Activités liées"],
        "forbidden_uses": ["Habitat", "Commerce grand public"],
        "height": {"max_floors": None, "label": "Restrictions aéronautiques (hauteur)"},
        "pap_required": True,
        "pap_type": "Autorisation DAC (Direction Aviation Civile)",
        "documents": [
            {
                "title": "Loi du 31 janvier 1948 – aviation civile",
                "url": "https://legilux.public.lu/",
                "type": "regulation",
            }
        ],
        "seco_touchpoints": ["CTC sur bâtiments techniques aéroportuaires"],
        "checklist": ["Coordination Direction Aviation Civile obligatoire", "Servitudes aéronautiques"],
        "color": "#334155",
    },
}

DEFAULT_RULE = {
    "name": "Zone non répertoriée",
    "density": "Non définie",
    "description": "Cette zone n'est pas encore répertoriée dans la base de données. Consulter le PAG communal.",
    "allowed_uses": [],
    "forbidden_uses": [],
    "height": {"max_floors": None, "label": "Inconnue"},
    "pap_required": False,
    "documents": [
        {
            "title": "Consulter le PAG communal via Géoportail",
            "url": "https://geoportail.lu/",
            "type": "communal",
        }
    ],
    "seco_touchpoints": [],
    "checklist": ["Consulter le PAG communal directement"],
    "color": "#e2e8f0",
}


def get_rule(categorie: str) -> dict:
    return ZONE_RULES.get(categorie, DEFAULT_RULE)
