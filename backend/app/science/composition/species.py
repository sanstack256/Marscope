"""
MARSCOPE Controlled Planetary Geochemical & Mineralogical Species Vocabulary
Martian Surface Intelligence & Exploration System

Defines canonical elements, stoichiometric oxides, crystalline minerals, and mineral groups
with normalized aliases, ambiguity detection, and supported analytical instrument pathways.
"""

import re
from typing import Dict, List, Optional, Tuple
from app.science.composition.models import (
    SpeciesCategory,
    SpeciesRecord,
    SpeciesResolutionResult,
)

# IUPAC Standard Atomic Weights (g/mol) used for stoichiometric oxide-to-element conversion
ATOMIC_WEIGHTS: Dict[str, float] = {
    "H": 1.008,
    "O": 15.999,
    "Na": 22.990,
    "Mg": 24.305,
    "Al": 26.982,
    "Si": 28.085,
    "P": 30.974,
    "S": 32.06,
    "Cl": 35.45,
    "K": 39.098,
    "Ca": 40.078,
    "Ti": 47.867,
    "Cr": 51.996,
    "Mn": 54.938,
    "Fe": 55.845,
    "Ni": 58.693,
    "Zn": 65.38,
    "Br": 79.904,
}


def _oxide_fraction(element_symbol: str, n_elem: int, n_ox: int) -> float:
    m_elem = n_elem * ATOMIC_WEIGHTS[element_symbol]
    m_total = m_elem + n_ox * ATOMIC_WEIGHTS["O"]
    return round(m_elem / m_total, 8)


def _norm_key(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", s.strip().lower())


def _build_vocabulary() -> Tuple[Dict[str, SpeciesRecord], Dict[str, List[str]]]:
    records: List[SpeciesRecord] = [
        # --- CHEMICAL ELEMENTS ---
        SpeciesRecord(
            canonical_id="Si",
            symbol_or_formula="Si",
            canonical_name="Silicon",
            category=SpeciesCategory.ELEMENT,
            aliases=["si", "silicon"],
            child_species=["SiO2"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Si"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
            notes="Measurable via calibrated SiO2 oxide stoichiometry (APXS, ChemCam MOC).",
        ),
        SpeciesRecord(
            canonical_id="Ti",
            symbol_or_formula="Ti",
            canonical_name="Titanium",
            category=SpeciesCategory.ELEMENT,
            aliases=["ti", "titanium"],
            child_species=["TiO2"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Ti"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Al",
            symbol_or_formula="Al",
            canonical_name="Aluminum",
            category=SpeciesCategory.ELEMENT,
            aliases=["al", "aluminum", "aluminium"],
            child_species=["Al2O3"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Al"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Fe",
            symbol_or_formula="Fe",
            canonical_name="Iron",
            category=SpeciesCategory.ELEMENT,
            aliases=["fe", "iron"],
            child_species=["FeO", "FeOT", "Fe2O3"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Fe"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Mg",
            symbol_or_formula="Mg",
            canonical_name="Magnesium",
            category=SpeciesCategory.ELEMENT,
            aliases=["mg", "magnesium"],
            child_species=["MgO"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Mg"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Ca",
            symbol_or_formula="Ca",
            canonical_name="Calcium",
            category=SpeciesCategory.ELEMENT,
            aliases=["ca", "calcium"],
            child_species=["CaO"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Ca"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Na",
            symbol_or_formula="Na",
            canonical_name="Sodium",
            category=SpeciesCategory.ELEMENT,
            aliases=["na", "sodium"],
            child_species=["Na2O"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Na"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="K",
            symbol_or_formula="K",
            canonical_name="Potassium",
            category=SpeciesCategory.ELEMENT,
            aliases=["k", "potassium"],
            child_species=["K2O"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["K"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="P",
            symbol_or_formula="P",
            canonical_name="Phosphorus",
            category=SpeciesCategory.ELEMENT,
            aliases=["p", "phosphorus"],
            child_species=["P2O5"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["P"],
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="Mn",
            symbol_or_formula="Mn",
            canonical_name="Manganese",
            category=SpeciesCategory.ELEMENT,
            aliases=["mn", "manganese"],
            child_species=["MnO"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Mn"],
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Cr",
            symbol_or_formula="Cr",
            canonical_name="Chromium",
            category=SpeciesCategory.ELEMENT,
            aliases=["cr", "chromium"],
            child_species=["Cr2O3"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Cr"],
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="S",
            symbol_or_formula="S",
            canonical_name="Sulfur",
            category=SpeciesCategory.ELEMENT,
            aliases=["s", "sulfur", "sulphur"],
            child_species=["SO3"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["S"],
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="Cl",
            symbol_or_formula="Cl",
            canonical_name="Chlorine",
            category=SpeciesCategory.ELEMENT,
            aliases=["cl", "chlorine", "chloride"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Cl"],
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="Ni",
            symbol_or_formula="Ni",
            canonical_name="Nickel",
            category=SpeciesCategory.ELEMENT,
            aliases=["ni", "nickel"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Ni"],
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="Zn",
            symbol_or_formula="Zn",
            canonical_name="Zinc",
            category=SpeciesCategory.ELEMENT,
            aliases=["zn", "zinc"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Zn"],
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="Br",
            symbol_or_formula="Br",
            canonical_name="Bromine",
            category=SpeciesCategory.ELEMENT,
            aliases=["br", "bromine"],
            atomic_or_molar_mass=ATOMIC_WEIGHTS["Br"],
            supported_instruments=["APXS"],
        ),
        # --- STOICHIOMETRIC OXIDES ---
        SpeciesRecord(
            canonical_id="SiO2",
            symbol_or_formula="SiO2",
            canonical_name="Silicon Dioxide (Bulk Oxide)",
            category=SpeciesCategory.OXIDE,
            aliases=["sio2", "silicondioxide"],
            associated_elements=["Si"],
            stoichiometric_element="Si",
            stoichiometric_mass_fraction=_oxide_fraction("Si", 1, 2),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="TiO2",
            symbol_or_formula="TiO2",
            canonical_name="Titanium Dioxide",
            category=SpeciesCategory.OXIDE,
            aliases=["tio2", "titaniumdioxide"],
            associated_elements=["Ti"],
            stoichiometric_element="Ti",
            stoichiometric_mass_fraction=_oxide_fraction("Ti", 1, 2),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Al2O3",
            symbol_or_formula="Al2O3",
            canonical_name="Aluminum Oxide (Alumina)",
            category=SpeciesCategory.OXIDE,
            aliases=["al2o3", "alumina", "aluminumoxide"],
            associated_elements=["Al"],
            stoichiometric_element="Al",
            stoichiometric_mass_fraction=_oxide_fraction("Al", 2, 3),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="FeO",
            symbol_or_formula="FeO",
            canonical_name="Iron(II) Oxide",
            category=SpeciesCategory.OXIDE,
            aliases=["feo"],
            associated_elements=["Fe"],
            stoichiometric_element="Fe",
            stoichiometric_mass_fraction=_oxide_fraction("Fe", 1, 1),
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="FeOT",
            symbol_or_formula="FeOT",
            canonical_name="Total Iron Reported as FeO",
            category=SpeciesCategory.OXIDE,
            aliases=["feot", "feototal"],
            associated_elements=["Fe"],
            stoichiometric_element="Fe",
            stoichiometric_mass_fraction=_oxide_fraction("Fe", 1, 1),
            supported_instruments=["ChemCam_LIBS", "APXS"],
        ),
        SpeciesRecord(
            canonical_id="Fe2O3",
            symbol_or_formula="Fe2O3",
            canonical_name="Iron(III) Oxide (Ferric Oxide)",
            category=SpeciesCategory.OXIDE,
            aliases=["fe2o3", "ferricoxide"],
            associated_elements=["Fe"],
            stoichiometric_element="Fe",
            stoichiometric_mass_fraction=_oxide_fraction("Fe", 2, 3),
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="MgO",
            symbol_or_formula="MgO",
            canonical_name="Magnesium Oxide",
            category=SpeciesCategory.OXIDE,
            aliases=["mgo", "magnesia"],
            associated_elements=["Mg"],
            stoichiometric_element="Mg",
            stoichiometric_mass_fraction=_oxide_fraction("Mg", 1, 1),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="CaO",
            symbol_or_formula="CaO",
            canonical_name="Calcium Oxide",
            category=SpeciesCategory.OXIDE,
            aliases=["cao"],
            associated_elements=["Ca"],
            stoichiometric_element="Ca",
            stoichiometric_mass_fraction=_oxide_fraction("Ca", 1, 1),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Na2O",
            symbol_or_formula="Na2O",
            canonical_name="Sodium Oxide",
            category=SpeciesCategory.OXIDE,
            aliases=["na2o"],
            associated_elements=["Na"],
            stoichiometric_element="Na",
            stoichiometric_mass_fraction=_oxide_fraction("Na", 2, 1),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="K2O",
            symbol_or_formula="K2O",
            canonical_name="Potassium Oxide",
            category=SpeciesCategory.OXIDE,
            aliases=["k2o", "potash"],
            associated_elements=["K"],
            stoichiometric_element="K",
            stoichiometric_mass_fraction=_oxide_fraction("K", 2, 1),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="P2O5",
            symbol_or_formula="P2O5",
            canonical_name="Phosphorus Pentoxide",
            category=SpeciesCategory.OXIDE,
            aliases=["p2o5"],
            associated_elements=["P"],
            stoichiometric_element="P",
            stoichiometric_mass_fraction=_oxide_fraction("P", 2, 5),
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="MnO",
            symbol_or_formula="MnO",
            canonical_name="Manganese(II) Oxide",
            category=SpeciesCategory.OXIDE,
            aliases=["mno"],
            associated_elements=["Mn"],
            stoichiometric_element="Mn",
            stoichiometric_mass_fraction=_oxide_fraction("Mn", 1, 1),
            supported_instruments=["APXS", "ChemCam_LIBS"],
        ),
        SpeciesRecord(
            canonical_id="Cr2O3",
            symbol_or_formula="Cr2O3",
            canonical_name="Chromium(III) Oxide",
            category=SpeciesCategory.OXIDE,
            aliases=["cr2o3"],
            associated_elements=["Cr"],
            stoichiometric_element="Cr",
            stoichiometric_mass_fraction=_oxide_fraction("Cr", 2, 3),
            supported_instruments=["APXS"],
        ),
        SpeciesRecord(
            canonical_id="SO3",
            symbol_or_formula="SO3",
            canonical_name="Sulfur Trioxide",
            category=SpeciesCategory.OXIDE,
            aliases=["so3"],
            associated_elements=["S"],
            stoichiometric_element="S",
            stoichiometric_mass_fraction=_oxide_fraction("S", 1, 3),
            supported_instruments=["APXS"],
        ),
        # --- MINERAL GROUPS ---
        SpeciesRecord(
            canonical_id="plagioclase",
            symbol_or_formula="(Na,Ca)(Al,Si)4O8",
            canonical_name="Plagioclase Feldspar Group",
            category=SpeciesCategory.MINERAL_GROUP,
            aliases=["plagioclase", "plag", "feldspar"],
            associated_elements=["Na", "Ca", "Al", "Si"],
            child_species=["andesine", "labradorite", "albite", "anorthite", "bytownite", "oligoclase"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="olivine",
            symbol_or_formula="(Mg,Fe)2SiO4",
            canonical_name="Olivine Group",
            category=SpeciesCategory.MINERAL_GROUP,
            aliases=["olivine"],
            associated_elements=["Mg", "Fe", "Si"],
            child_species=["forsterite", "fayalite"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="pyroxene",
            symbol_or_formula="(Ca,Na,Fe,Mg)(Mg,Fe,Al)(Si,Al)2O6",
            canonical_name="Pyroxene Group",
            category=SpeciesCategory.MINERAL_GROUP,
            aliases=["pyroxene"],
            associated_elements=["Ca", "Mg", "Fe", "Al", "Si"],
            child_species=["augite", "pigeonite", "orthopyroxene", "enstatite", "diopside"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="smectite",
            symbol_or_formula="(Na,Ca)0.3(Al,Mg,Fe)2-3(Si,Al)4O10(OH)2·nH2O",
            canonical_name="Smectite Phyllosilicate Group",
            category=SpeciesCategory.MINERAL_GROUP,
            aliases=["smectite", "phyllosilicate", "clay", "clays", "claymineral"],
            associated_elements=["Si", "Al", "Fe", "Mg", "Ca", "Na"],
            child_species=["montmorillonite", "nontronite", "saponite", "illite", "chlorite", "kaolinite"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="sulfate",
            symbol_or_formula="SO4²⁻ Minerals",
            canonical_name="Sulfate Mineral Group",
            category=SpeciesCategory.MINERAL_GROUP,
            aliases=["sulfate", "sulfates", "sulphate", "casulfate", "casulfates"],
            associated_elements=["S", "Ca", "Mg", "Fe"],
            child_species=["gypsum", "bassanite", "anhydrite", "jarosite", "starkeyite", "kieserite", "epsomite"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="carbonate",
            symbol_or_formula="CO3²⁻ Minerals",
            canonical_name="Carbonate Mineral Group",
            category=SpeciesCategory.MINERAL_GROUP,
            aliases=["carbonate", "carbonates"],
            associated_elements=["Ca", "Mg", "Fe", "Mn"],
            child_species=["calcite", "magnesite", "siderite", "dolomite"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        # --- CRYSTALLINE MINERALS (CHEMIN / MARS) ---
        SpeciesRecord(
            canonical_id="andesine",
            symbol_or_formula="(Ca,Na)(Al,Si)4O8",
            canonical_name="Andesine",
            category=SpeciesCategory.MINERAL,
            aliases=["andesine"],
            associated_elements=["Ca", "Na", "Al", "Si"],
            parent_group="plagioclase",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="labradorite",
            symbol_or_formula="(Ca,Na)(Al,Si)4O8",
            canonical_name="Labradorite",
            category=SpeciesCategory.MINERAL,
            aliases=["labradorite"],
            associated_elements=["Ca", "Na", "Al", "Si"],
            parent_group="plagioclase",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="albite",
            symbol_or_formula="NaAlSi3O8",
            canonical_name="Albite",
            category=SpeciesCategory.MINERAL,
            aliases=["albite"],
            associated_elements=["Na", "Al", "Si"],
            parent_group="plagioclase",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="anorthite",
            symbol_or_formula="CaAl2Si2O8",
            canonical_name="Anorthite",
            category=SpeciesCategory.MINERAL,
            aliases=["anorthite"],
            associated_elements=["Ca", "Al", "Si"],
            parent_group="plagioclase",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="sanidine",
            symbol_or_formula="KAlSi3O8",
            canonical_name="Sanidine (K-Feldspar)",
            category=SpeciesCategory.MINERAL,
            aliases=["sanidine", "kfeldspar", "orthoclase"],
            associated_elements=["K", "Al", "Si"],
            parent_group="plagioclase",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="forsterite",
            symbol_or_formula="Mg2SiO4",
            canonical_name="Forsterite",
            category=SpeciesCategory.MINERAL,
            aliases=["forsterite"],
            associated_elements=["Mg", "Si"],
            parent_group="olivine",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="fayalite",
            symbol_or_formula="Fe2SiO4",
            canonical_name="Fayalite",
            category=SpeciesCategory.MINERAL,
            aliases=["fayalite"],
            associated_elements=["Fe", "Si"],
            parent_group="olivine",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="augite",
            symbol_or_formula="(Ca,Na)(Mg,Fe,Al,Ti)(Si,Al)2O6",
            canonical_name="Augite",
            category=SpeciesCategory.MINERAL,
            aliases=["augite"],
            associated_elements=["Ca", "Mg", "Fe", "Al", "Ti", "Si"],
            parent_group="pyroxene",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="pigeonite",
            symbol_or_formula="(Mg,Fe,Ca)(Mg,Fe)Si2O6",
            canonical_name="Pigeonite",
            category=SpeciesCategory.MINERAL,
            aliases=["pigeonite"],
            associated_elements=["Mg", "Fe", "Ca", "Si"],
            parent_group="pyroxene",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="orthopyroxene",
            symbol_or_formula="(Mg,Fe)SiO3",
            canonical_name="Orthopyroxene",
            category=SpeciesCategory.MINERAL,
            aliases=["orthopyroxene", "opx", "enstatite", "ferrosilite"],
            associated_elements=["Mg", "Fe", "Si"],
            parent_group="pyroxene",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="hematite",
            symbol_or_formula="Fe2O3",
            canonical_name="Hematite",
            category=SpeciesCategory.MINERAL,
            aliases=["hematite", "haematite"],
            associated_elements=["Fe"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="magnetite",
            symbol_or_formula="Fe3O4",
            canonical_name="Magnetite",
            category=SpeciesCategory.MINERAL,
            aliases=["magnetite"],
            associated_elements=["Fe"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="akaganeite",
            symbol_or_formula="beta-FeO(OH,Cl)",
            canonical_name="Akaganeite",
            category=SpeciesCategory.MINERAL,
            aliases=["akaganeite", "akaganeitecl"],
            associated_elements=["Fe", "Cl", "H"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="goethite",
            symbol_or_formula="FeO(OH)",
            canonical_name="Goethite",
            category=SpeciesCategory.MINERAL,
            aliases=["goethite"],
            associated_elements=["Fe", "H"],
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="ilmenite",
            symbol_or_formula="FeTiO3",
            canonical_name="Ilmenite",
            category=SpeciesCategory.MINERAL,
            aliases=["ilmenite"],
            associated_elements=["Fe", "Ti"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="anhydrite",
            symbol_or_formula="CaSO4",
            canonical_name="Anhydrite",
            category=SpeciesCategory.MINERAL,
            aliases=["anhydrite"],
            associated_elements=["Ca", "S"],
            parent_group="sulfate",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="bassanite",
            symbol_or_formula="CaSO4·0.5H2O",
            canonical_name="Bassanite",
            category=SpeciesCategory.MINERAL,
            aliases=["bassanite"],
            associated_elements=["Ca", "S", "H"],
            parent_group="sulfate",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="gypsum",
            symbol_or_formula="CaSO4·2H2O",
            canonical_name="Gypsum",
            category=SpeciesCategory.MINERAL,
            aliases=["gypsum"],
            associated_elements=["Ca", "S", "H"],
            parent_group="sulfate",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="jarosite",
            symbol_or_formula="KFe3(SO4)2(OH)6",
            canonical_name="Jarosite",
            category=SpeciesCategory.MINERAL,
            aliases=["jarosite"],
            associated_elements=["K", "Fe", "S", "H"],
            parent_group="sulfate",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="starkeyite",
            symbol_or_formula="MgSO4·4H2O",
            canonical_name="Starkeyite",
            category=SpeciesCategory.MINERAL,
            aliases=["starkeyite"],
            associated_elements=["Mg", "S", "H"],
            parent_group="sulfate",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="montmorillonite",
            symbol_or_formula="(Na,Ca)0.33(Al,Mg)2Si4O10(OH)2·nH2O",
            canonical_name="Montmorillonite",
            category=SpeciesCategory.MINERAL,
            aliases=["montmorillonite"],
            associated_elements=["Na", "Ca", "Al", "Mg", "Si", "H"],
            parent_group="smectite",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="nontronite",
            symbol_or_formula="Na0.3Fe2(Si,Al)4O10(OH)2·nH2O",
            canonical_name="Nontronite",
            category=SpeciesCategory.MINERAL,
            aliases=["nontronite"],
            associated_elements=["Na", "Fe", "Si", "Al", "H"],
            parent_group="smectite",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="saponite",
            symbol_or_formula="Ca0.25(Mg,Fe)3((Si,Al)4O10)(OH)2·nH2O",
            canonical_name="Saponite",
            category=SpeciesCategory.MINERAL,
            aliases=["saponite"],
            associated_elements=["Ca", "Mg", "Fe", "Si", "Al", "H"],
            parent_group="smectite",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="illite",
            symbol_or_formula="(K,H3O)Al2(Si3Al)O10(OH)2",
            canonical_name="Illite",
            category=SpeciesCategory.MINERAL,
            aliases=["illite"],
            associated_elements=["K", "Al", "Si", "H"],
            parent_group="smectite",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="chlorite",
            symbol_or_formula="(Mg,Fe)5Al(Si3Al)O10(OH)8",
            canonical_name="Chlorite",
            category=SpeciesCategory.MINERAL,
            aliases=["chlorite"],
            associated_elements=["Mg", "Fe", "Al", "Si", "H"],
            parent_group="smectite",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="kaolinite",
            symbol_or_formula="Al2Si2O5(OH)4",
            canonical_name="Kaolinite",
            category=SpeciesCategory.MINERAL,
            aliases=["kaolinite"],
            associated_elements=["Al", "Si", "H"],
            parent_group="smectite",
            supported_instruments=["CheMin_XRD", "CRISM"],
        ),
        SpeciesRecord(
            canonical_id="quartz",
            symbol_or_formula="SiO2",
            canonical_name="Quartz",
            category=SpeciesCategory.MINERAL,
            aliases=["quartz"],
            associated_elements=["Si"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="tridymite",
            symbol_or_formula="SiO2",
            canonical_name="Tridymite",
            category=SpeciesCategory.MINERAL,
            aliases=["tridymite"],
            associated_elements=["Si"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="cristobalite",
            symbol_or_formula="SiO2",
            canonical_name="Cristobalite",
            category=SpeciesCategory.MINERAL,
            aliases=["cristobalite"],
            associated_elements=["Si"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="calcite",
            symbol_or_formula="CaCO3",
            canonical_name="Calcite",
            category=SpeciesCategory.MINERAL,
            aliases=["calcite"],
            associated_elements=["Ca"],
            parent_group="carbonate",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="siderite",
            symbol_or_formula="FeCO3",
            canonical_name="Siderite",
            category=SpeciesCategory.MINERAL,
            aliases=["siderite"],
            associated_elements=["Fe"],
            parent_group="carbonate",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="magnesite",
            symbol_or_formula="MgCO3",
            canonical_name="Magnesite",
            category=SpeciesCategory.MINERAL,
            aliases=["magnesite"],
            associated_elements=["Mg"],
            parent_group="carbonate",
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="halite",
            symbol_or_formula="NaCl",
            canonical_name="Halite",
            category=SpeciesCategory.MINERAL,
            aliases=["halite", "rocksait"],
            associated_elements=["Na", "Cl"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="fluorapatite",
            symbol_or_formula="Ca5(PO4)3F",
            canonical_name="Fluorapatite",
            category=SpeciesCategory.MINERAL,
            aliases=["fluorapatite", "apatite"],
            associated_elements=["Ca", "P"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="pyrite",
            symbol_or_formula="FeS2",
            canonical_name="Pyrite",
            category=SpeciesCategory.MINERAL,
            aliases=["pyrite"],
            associated_elements=["Fe", "S"],
            supported_instruments=["CheMin_XRD"],
        ),
        SpeciesRecord(
            canonical_id="pyrrhotite",
            symbol_or_formula="Fe(1-x)S",
            canonical_name="Pyrrhotite",
            category=SpeciesCategory.MINERAL,
            aliases=["pyrrhotite"],
            associated_elements=["Fe", "S"],
            supported_instruments=["CheMin_XRD"],
        ),
    ]

    by_id: Dict[str, SpeciesRecord] = {r.canonical_id: r for r in records}
    alias_map: Dict[str, List[str]] = {}
    for r in records:
        keys = {_norm_key(r.canonical_id), _norm_key(r.canonical_name)}
        keys.update(_norm_key(a) for a in r.aliases)
        for k in keys:
            if k:
                alias_map.setdefault(k, [])
                if r.canonical_id not in alias_map[k]:
                    alias_map[k].append(r.canonical_id)

    # Explicitly curated ambiguous geological queries
    alias_map["silica"] = ["SiO2", "quartz", "tridymite", "cristobalite"]
    alias_map["ironoxide"] = ["hematite", "magnetite", "goethite", "akaganeite", "FeOT"]
    alias_map["al"]  # ensure present
    return by_id, alias_map


SPECIES_VOCABULARY, _ALIAS_INDEX = _build_vocabulary()


def list_all_species() -> List[SpeciesRecord]:
    return sorted(SPECIES_VOCABULARY.values(), key=lambda s: (s.category.value, s.canonical_id.lower()))


def get_species_by_id(canonical_id: str) -> Optional[SpeciesRecord]:
    return SPECIES_VOCABULARY.get(canonical_id)


def resolve_species_query(raw_query: str) -> SpeciesResolutionResult:
    """
    Resolve a user or dataset species string against the controlled MARSCOPE vocabulary.
    Detects ambiguous shorthand terms rather than silently picking an arbitrary mineral or element.
    """
    norm = _norm_key(raw_query)
    if not norm:
        return SpeciesResolutionResult(
            raw_query=raw_query,
            normalized_query=norm,
            resolved=False,
            ambiguous=False,
            explanation="Empty species query.",
        )

    # Direct exact case-insensitive canonical match
    for cid, rec in SPECIES_VOCABULARY.items():
        if raw_query.strip().lower() == cid.lower():
            return SpeciesResolutionResult(
                raw_query=raw_query,
                normalized_query=norm,
                resolved=True,
                ambiguous=False,
                species=rec,
                candidates=[rec],
                explanation=f"Exact match to canonical {rec.category.value} '{rec.canonical_id}'.",
            )

    matched_ids = _ALIAS_INDEX.get(norm, [])
    if len(matched_ids) == 1:
        rec = SPECIES_VOCABULARY[matched_ids[0]]
        return SpeciesResolutionResult(
            raw_query=raw_query,
            normalized_query=norm,
            resolved=True,
            ambiguous=False,
            species=rec,
            candidates=[rec],
            explanation=f"Normalized alias match to {rec.category.value} '{rec.canonical_id}' ({rec.canonical_name}).",
        )

    if len(matched_ids) > 1:
        cands = [SPECIES_VOCABULARY[cid] for cid in matched_ids]
        return SpeciesResolutionResult(
            raw_query=raw_query,
            normalized_query=norm,
            resolved=False,
            ambiguous=True,
            candidates=cands,
            explanation=(
                f"Query '{raw_query}' is scientifically ambiguous and maps to multiple species: "
                + ", ".join(c.canonical_id for c in cands)
                + ". Specify canonical oxide, element, or crystalline phase."
            ),
        )

    # Partial prefix/substring suggestions (never silent match)
    suggestions = [
        rec
        for rec in SPECIES_VOCABULARY.values()
        if norm in _norm_key(rec.canonical_id) or norm in _norm_key(rec.canonical_name)
    ]
    return SpeciesResolutionResult(
        raw_query=raw_query,
        normalized_query=norm,
        resolved=False,
        ambiguous=len(suggestions) > 1,
        candidates=suggestions[:10],
        explanation=(
            f"Species '{raw_query}' not found in controlled MARSCOPE planetary geochemistry vocabulary."
            + (
                f" Closest canonical candidates: {', '.join(s.canonical_id for s in suggestions[:5])}."
                if suggestions
                else ""
            )
        ),
    )


def get_child_minerals_for_group(group_id: str) -> List[str]:
    rec = SPECIES_VOCABULARY.get(group_id)
    if not rec:
        return []
    return list(rec.child_species)


def get_element_bearing_minerals(element_id: str) -> List[str]:
    return [
        rec.canonical_id
        for rec in SPECIES_VOCABULARY.values()
        if rec.category in {SpeciesCategory.MINERAL, SpeciesCategory.MINERAL_GROUP}
        and element_id in rec.associated_elements
    ]
