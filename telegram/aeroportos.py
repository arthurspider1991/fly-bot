"""
telegram/aeroportos.py — Dados IATA do Brasil e América do Sul.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))



BRASIL_ESTADOS = {
    "AC": "Acre",            "AL": "Alagoas",          "AM": "Amazonas",
    "AP": "Amapá",           "BA": "Bahia",            "CE": "Ceará",
    "DF": "Distrito Federal","ES": "Espírito Santo",   "GO": "Goiás",
    "MA": "Maranhão",        "MG": "Minas Gerais",     "MS": "Mato Grosso do Sul",
    "MT": "Mato Grosso",     "PA": "Pará",             "PB": "Paraíba",
    "PE": "Pernambuco",      "PI": "Piauí",            "PR": "Paraná",
    "RJ": "Rio de Janeiro",  "RN": "Rio Grande do Norte","RO": "Rondônia",
    "RR": "Roraima",         "RS": "Rio Grande do Sul","SC": "Santa Catarina",
    "SE": "Sergipe",         "SP": "São Paulo",        "TO": "Tocantins",
}

BRASIL_AEROPORTOS = {
    "AC": [("RBR","Rio Branco")],
    "AL": [("MCZ","Maceió")],
    "AM": [("MAO","Manaus"),("TBT","Tabatinga"),("MNX","Manicoré"),("PIN","Parintins")],
    "AP": [("MCP","Macapá")],
    "BA": [("SSA","Salvador"),("IOS","Ilhéus"),("BPS","Porto Seguro"),("PAV","Paulo Afonso"),("FEC","Feira de Santana")],
    "CE": [("FOR","Fortaleza"),("JDO","Juazeiro do Norte")],
    "DF": [("BSB","Brasília")],
    "ES": [("VIX","Vitória")],
    "GO": [("GYN","Goiânia")],
    "MA": [("SLZ","São Luís"),("IMP","Imperatriz")],
    "MG": [("CNF","BH - Confins"),("PLU","BH - Pampulha"),("UDI","Uberlândia"),
           ("UBA","Uberaba"),("MOC","Montes Claros"),("GVR","Gov. Valadares"),
           ("IPH","Ipatinga"),("DIQ","Divinópolis"),("VAG","Varginha")],
    "MS": [("CGR","Campo Grande")],
    "MT": [("CGB","Cuiabá")],
    "PA": [("BEL","Belém"),("MAB","Marabá"),("CKS","Carajás"),("STM","Santarém"),
           ("ITB","Itaituba"),("ATM","Altamira"),("SFK","Soure/Marajó")],
    "PB": [("JPA","João Pessoa"),("CPV","Campina Grande")],
    "PE": [("REC","Recife")],
    "PI": [("THE","Teresina")],
    "PR": [("CWB","Curitiba"),("CAC","Cascavel"),("LDB","Londrina"),("MGF","Maringá")],
    "RJ": [("GIG","Rio - Galeão"),("SDU","Rio - Santos Dumont"),("CAW","Campos"),("CFB","Cabo Frio")],
    "RN": [("NAT","Natal")],
    "RO": [("PVH","Porto Velho"),("OAL","Cacoal")],
    "RR": [("BVB","Boa Vista")],
    "RS": [("POA","Porto Alegre"),("PFB","Passo Fundo"),("RIG","Rio Grande"),("SRA","Santa Rosa")],
    "SC": [("FLN","Florianópolis"),("JOI","Joinville"),("NVT","Navegantes"),("XAP","Chapecó")],
    "SE": [("AJU","Aracaju")],
    "SP": [("GRU","SP - Guarulhos"),("CGH","SP - Congonhas"),("VCP","Campinas"),
           ("RAO","Ribeirão Preto"),("BAU","Bauru"),("ARU","Araçatuba"),
           ("PPB","Pres. Prudente"),("MII","Marília")],
    "TO": [("PMW","Palmas")],
}

OUTROS_PAISES = {
    "🇦🇷 Argentina":  [("EZE","Buenos Aires - Ezeiza"),("AEP","Buenos Aires - Aeroparque"),
                       ("COR","Córdoba"),("MDZ","Mendoza"),("ROS","Rosario"),("BRC","Bariloche"),
                       ("IGR","Puerto Iguazú"),("SLA","Salta"),("TUC","Tucumán"),("USH","Ushuaia"),
                       ("FTE","El Calafate"),("PMY","Puerto Madryn"),("NQN","Neuquén")],
    "🇨🇱 Chile":      [("SCL","Santiago"),("PMC","Puerto Montt"),("PUQ","Punta Arenas"),
                       ("IQQ","Iquique"),("ANF","Antofagasta"),("CJC","Calama"),
                       ("ZCO","Temuco"),("ZAL","Valdivia")],
    "🇨🇴 Colômbia":   [("BOG","Bogotá"),("MDE","Medellín"),("CLO","Cali"),("CTG","Cartagena"),
                       ("BAQ","Barranquilla"),("SMR","Santa Marta"),("PEI","Pereira")],
    "🇵🇪 Peru":       [("LIM","Lima"),("CUZ","Cusco"),("AQP","Arequipa"),("IQT","Iquitos"),("TRU","Trujillo")],
    "🇪🇨 Equador":    [("UIO","Quito"),("GYE","Guayaquil"),("GPS","Galápagos")],
    "🇧🇴 Bolívia":    [("VVI","Santa Cruz"),("LPB","La Paz"),("CBB","Cochabamba"),("SRE","Sucre")],
    "🇺🇾 Uruguai":    [("MVD","Montevidéu"),("PDP","Punta del Este")],
    "🇵🇾 Paraguai":   [("ASU","Assunção")],
    "🇻🇪 Venezuela":  [("CCS","Caracas"),("MAR","Maracaibo")],
    "🇬🇾 Guiana":     [("GEO","Georgetown")],
    "🇸🇷 Suriname":   [("PBM","Paramaribo")],
    "🇬🇫 Guiana Fr.": [("CAY","Caiena")],
    "🇵🇦 Panamá":     [("PTY","Cidade do Panamá")],
    "🇲🇽 México":     [("MEX","Cidade do México"),("CUN","Cancún")],
}

# Flat dict para lookup rápido
AEROPORTOS: dict[str, str] = {}
for _lista in BRASIL_AEROPORTOS.values():
    for _iata, _nome in _lista:
        AEROPORTOS[_iata] = _nome
for _lista in OUTROS_PAISES.values():
    for _iata, _nome in _lista:
        AEROPORTOS[_iata] = _nome
