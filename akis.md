# DAHAO Sidecar - Proje Akis Dokumantasyonu

Bu dokuman, Leviathan/DAHAO sidecar projesinin tum akisini ve bilesenlerini detayli olarak aciklar.

---

## Genel Bakis

**Leviathan**, Cosmos tabanli DAHAO blockchain'i icin otonom bir yonetisim oylama ajanıdır. Sistem, zincir uzerindeki yonetisim tekliflerini izler ve kullanicinin tanimladigi ilkelere (Fork) gore LLM destekli oylama kararlari alir.

```
┌─────────────────────────────────────────────────────────┐
│                    DAHAO Sidecar (Python)               │
│  ┌──────────┐   ┌──────────┐   ┌──────────────────┐    │
│  │  Chain   │◄──│ Sidecar  │──►│      Brain       │    │
│  │ (CosmPy) │   │  Loop    │   │    (Ollama)      │    │
│  └────┬─────┘   └────┬─────┘   └────────┬─────────┘    │
│       │              │                   │              │
│       ▼              ▼                   ▼              │
│  ┌──────────┐  ┌──────────┐        ┌──────────┐        │
│  │ Wallet   │  │  Shared  │        │   Fork   │        │
│  │(mnemonic)│  │   Law    │        │ (values) │        │
│  └──────────┘  └──────────┘        └──────────┘        │
└─────────────────────────────────────────────────────────┘
         │              │                   │
         ▼              ▼                   ▼
   ┌───────────┐  ┌───────────┐      ┌───────────┐
   │  Cosmos   │  │  data/    │      │  Ollama   │
   │   Chain   │  │  *.json   │      │  Server   │
   └───────────┘  └───────────┘      └───────────┘
```

---

## 1. Proje Yapisi

```
leviathan/
├── main.py                 # Ana giris noktasi
├── config.yaml             # Zincir, LLM, sidecar ayarlari
├── fork.yaml               # Kullanicinin oylama ilkeleri
├── simulation_swarm.py     # Coklu ajan simulasyon sistemi
├── submit_test_proposals.py # Test teklif gonderme
├── monitor.py              # Streamlit karar izleme panosu
├── decisions.log           # Oylama denetim kayitlari
│
├── adapter/                # Kimlik Adaptoru modulu
│   ├── __init__.py         # Modul ihraclari
│   ├── models.py           # Persona modeli
│   ├── loader.py           # PersonaLoader sinifi
│   ├── mapper.py           # PersonaMapper (LLM donusumu)
│   ├── prompts.py          # LLM semalari ve promptlar
│   └── cache.py            # ForkCache onbellekleme
│
├── config/                 # Yapilandirma modulleri
│   ├── settings.py         # Pydantic ayarlar
│   └── fork.py             # Fork modeli ve dogrulama
│
├── chain/                  # Blockchain etkilesimi
│   ├── client.py           # LedgerClient + gRPC sarmalayici
│   ├── governance.py       # Teklif sorgulama, oy gonderme
│   └── wallet.py           # Cuzdan yonetimi
│
├── brain/                  # LLM karar mekanizmasi
│   ├── llm.py              # Ollama sarmalayici
│   ├── prompts.py          # Oylama promptlari
│   └── decision.py         # Karar motoru
│
├── sidecar/                # Ana dongü ve durum yonetimi
│   ├── loop.py             # Asenkron sorgulama dongusu
│   ├── state.py            # Islenmis teklif takibi
│   └── logger.py           # Karar denetim gunlugu
│
├── models/                 # Veri modelleri
│   ├── proposal.py         # Teklif sinifi
│   └── vote.py             # Oy secenekleri ve karar
│
├── data/                   # SharedLaw yonetisim cercevesi
│   ├── terms.json          # Evrensel terimler sozlugu
│   ├── principles.json     # Temel ilkeler
│   ├── rules.json          # Yonetisim kurallari
│   ├── governance.json     # Esikler ve zamanlamalar
│   └── domains.json        # Alan kayit defteri
│
└── simulation/             # Coklu ajan simulasyonu
    ├── *_persona.json      # Ajan persona dosyalari
    ├── proposals/          # Test teklifleri
    └── wallets.yaml        # Test cuzdan bilgileri
```

---

## 2. Tam Calisma Akisi

### 2.1 Baslangic Akisi (main.py)

```
python main.py --persona persona.json --wallet "24 kelimelik mnemonic" --name Alice
# veya: python main.py --fork fork.yaml --wallet "..." --name Alice
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. YAPILANDIRMA YUKLEME                                         │
│    ├─ config.yaml → ChainConfig + LLMConfig + SidecarConfig     │
│    ├─ --persona verilmisse: persona.json → Kimlik Adaptoru      │
│    │     └─ LLM ile Fork'a donusturulur (asagida detayli)      │
│    ├─ --persona verilmemisse: fork.yaml → Fork                  │
│    └─ data/*.json → SharedLaw (kilit ilkeler, terimler)         │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. FORK DOGRULAMA                                               │
│    ├─ Fork'un kullandigi terimlerin SharedLaw'da mevcut olmasi  │
│    ├─ Fork ilkelerinin kilit ilkeleri ihlal etmemesi            │
│    └─ LLM semantik dogrulama (opsiyonel)                        │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. BILESEN BASLIATMA                                            │
│    ├─ ChainClient → gRPC baglantisi (localhost:9090)            │
│    ├─ WalletManager → 24 kelimelik mnemonic'ten cuzdan          │
│    ├─ Bakiye Kontrolu → Minimum 1000 stake                      │
│    ├─ LLMWrapper → Ollama baglantisi (localhost:11434)          │
│    ├─ DecisionEngine → LLM + Fork + SharedLaw birlestirme       │
│    ├─ GovernanceClient → Teklif sorgulama                       │
│    └─ SidecarState → Onceden islenmis teklifleri yukle          │
└─────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. SIDECAR DONGUSU BASLATMA                                     │
│    └─ SidecarLoop.run() → Asenkron ana dongü                    │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 Kimlik Adaptoru Akisi (adapter/)

Harici persona.json dosyalarini (Journal App'ten) gecerli Fork yapilandirmalarina donusturur.

**Persona Formati (persona.json):**
```json
{
  "user_id": "alice_123",
  "archetype": "Deep Ecologist",
  "core_values": [
    "Doga, insan faydasindan bagimsiz olarak haklara sahiptir",
    "Ekosistemlere zarar veriyorsa teknoloji yavaslatilmali",
    "Mahremiyet bireysel ozgurluk icin gereklidir"
  ],
  "decision_style": "Yuksek dikkat, guclu kanit gerektirir",
  "last_updated": "2026-01-29T14:00:00Z"
}
```

**Donusum Akisi:**
```
persona.json
      │
      ▼
┌─────────────────────────────────────────────────────────────────┐
│ PersonaLoader                                                    │
│   ├─ CLI arg → ./persona.json → ~/.config/dahao/persona.json    │
│   └─ load_or_raise() → Persona objesi                           │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ PersonaMapper (LLM tabanli)                                      │
│   ├─ SharedLaw'dan terimler ve ilkeleri al                       │
│   ├─ System prompt olustur (gecerli aligns_with degerleri)       │
│   ├─ LLM'e persona detaylarini gonder                            │
│   └─ JSON cikti al:                                              │
│       {                                                          │
│         "name": "Deep Ecologist Node",                          │
│         "inherits": "dahao-core v1.0.0",                        │
│         "uses_terms": ["@protection", "@harm"],                 │
│         "principles": [                                         │
│           {                                                      │
│             "statement": "Ekosistemlere zarar veren...",        │
│             "aligns_with": "@precautionary_default"             │
│           }                                                      │
│         ],                                                       │
│         "voting_style": "cautious",                             │
│         "abstain_threshold": 0.7                                │
│       }                                                          │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Dogrulama                                                        │
│   ├─ aligns_with sadece ILKE adlari olmali (terim degil!)       │
│   │     ✓ Gecerli: @precautionary_default, @purpose_primacy     │
│   │     ✗ Gecersiz: @protection, @harm (bunlar TERİM)           │
│   ├─ Kilit ilkelere karsi kontrol                                │
│   └─ Hata varsa → fail-fast (ajan baslamaz)                     │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ ForkCache (opsiyonel)                                            │
│   ├─ Konum: ~/.cache/dahao/forks/fork_{hash}.yaml               │
│   ├─ Anahtar: SHA256(persona_content + shared_law_version)       │
│   └─ Inceleme icin YAML olarak kaydedilir                       │
└─────────────────────────────────────────────────────────────────┘
```

**Terim vs Ilke (Onemli Ayrım):**

| Kavram | Ornekler | Kullanildigi Yer |
|--------|----------|------------------|
| **Terim** | `@protection`, `@harm`, `@evidence` | `uses_terms` dizisi |
| **Ilke** | `@precautionary_default`, `@purpose_primacy` | `aligns_with` alani |

`aligns_with` alaninda terim kullanilirsa dogrulama hatasi verir.

### 2.3 Ana Dongu Akisi (sidecar/loop.py)

```
┌─────────────────────────────────────────────────────────────────┐
│                     SidecarLoop.run()                            │
│                    (Asenkron Ana Dongu)                          │
└─────────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┴───────────────────┐
        │                                       │
        ▼                                       ▼
┌───────────────┐                      ┌───────────────┐
│ Sinyal Isleme │                      │ _poll_cycle() │◄─────┐
│ SIGTERM/INT   │                      │ (Her donemde) │      │
│ → _running=F  │                      └───────┬───────┘      │
└───────────────┘                              │              │
                                               ▼              │
                               ┌───────────────────────────┐  │
                               │ governance.fetch_voting_  │  │
                               │ proposals()               │  │
                               │ → Oylama donemindeki      │  │
                               │   teklifleri getir        │  │
                               └─────────────┬─────────────┘  │
                                             │                │
                                             ▼                │
                               ┌───────────────────────────┐  │
                               │ Her islenmemis teklif:    │  │
                               │ state.is_processed()?     │  │
                               │ → Hayir ise isle          │  │
                               └─────────────┬─────────────┘  │
                                             │                │
                                             ▼                │
                               ┌───────────────────────────┐  │
                               │ _process_proposal()       │  │
                               │ (Asagida detayli)         │  │
                               └─────────────┬─────────────┘  │
                                             │                │
                                             ▼                │
                               ┌───────────────────────────┐  │
                               │ asyncio.sleep             │  │
                               │ (poll_interval_seconds)   │──┘
                               └───────────────────────────┘
```

### 2.4 Teklif Isleme Akisi

```
_process_proposal(proposal)
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. KARAR ALMA                                                    │
│    decision_engine.decide(proposal)                             │
│                                                                  │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │ a) build_voting_prompt()                                │  │
│    │    ├─ SharedLaw varsa: Kilit ilkeler + Terimler        │  │
│    │    ├─ Fork ilkeleri ve oylama stili                    │  │
│    │    └─ Teklif ozeti (baslik + aciklama)                 │  │
│    │                                                        │  │
│    │ b) LLM.generate_vote_decision()                        │  │
│    │    ├─ Prompt'u Ollama'ya gonder                        │  │
│    │    ├─ JSON schema zorunlulugu (VOTE_SCHEMA)            │  │
│    │    └─ {vote, confidence, reasoning} al                 │  │
│    │                                                        │  │
│    │ c) Abstain threshold uygula                            │  │
│    │    └─ confidence < threshold → ABSTAIN                 │  │
│    └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│    Sonuc: VoteDecision(choice, confidence, reasoning)           │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. KAYIT TUTMA                                                   │
│    log_decision(proposal, decision, fork, shared_law)           │
│                                                                  │
│    decisions.log'a yazilan veriler:                             │
│    ├─ timestamp: ISO-8601 UTC                                   │
│    ├─ proposal_id, proposal_title                               │
│    ├─ fork_name                                                 │
│    ├─ vote: YES/NO/ABSTAIN/NO_WITH_VETO                        │
│    ├─ confidence: 0.0-1.0                                       │
│    ├─ llm_reasoning: LLM'in aciklamasi                         │
│    ├─ reasoning_hash: SHA256 (zincire gondermek icin)          │
│    └─ SharedLaw baglami (varsa):                               │
│        ├─ terms_referenced                                      │
│        ├─ principles_aligned                                    │
│        ├─ locked_constraints                                    │
│        └─ governance_version                                    │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. OY GONDERME                                                   │
│    _submit_vote(proposal, decision)                             │
│                                                                  │
│    ┌─────────────────────────────────────────────────────────┐  │
│    │ a) MsgVote olustur                                      │  │
│    │    ├─ proposal_id: Teklif ID                           │  │
│    │    ├─ voter: Cuzdan adresi                             │  │
│    │    └─ option: VOTE_OPTION_YES/NO/ABSTAIN/VETO          │  │
│    │                                                        │  │
│    │ b) Transaction olustur                                  │  │
│    │    ├─ tx.add_message(msg)                              │  │
│    │    ├─ Gas ve ucret hesapla                             │  │
│    │    ├─ tx.seal() - Imza yapisi                          │  │
│    │    ├─ tx.sign() - Ozel anahtar ile imzala              │  │
│    │    └─ tx.complete() - Tamamla                          │  │
│    │                                                        │  │
│    │ c) Zincire yayinla                                      │  │
│    │    ├─ ledger.broadcast_tx(tx)                          │  │
│    │    └─ wait_to_complete() - Islem onayini bekle         │  │
│    └─────────────────────────────────────────────────────────┘  │
│                                                                  │
│    Hata durumunda: retry_count++ ve tekrar dene (max 3)         │
└──────────────────────────────┬──────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. DURUM GUNCELLEME                                              │
│    state.mark_processed(proposal.id)                            │
│    → JSON dosyasina kaydet (sidecar_state.json)                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 3. LLM Karar Mekanizmasi (brain/)

### 3.1 Karar Motoru (decision.py)

```
┌─────────────────────────────────────────────────────────────────┐
│                    DecisionEngine                                │
├─────────────────────────────────────────────────────────────────┤
│ Girisler:                                                        │
│   ├─ Proposal (baslik, aciklama, ID, tarihler)                  │
│   ├─ Fork (ilkeler, oylama_stili, abstain_threshold)            │
│   └─ SharedLaw (kilit_ilkeler, terimler, esikler)               │
├─────────────────────────────────────────────────────────────────┤
│ Islem:                                                           │
│   1. build_voting_prompt() → LLM icin prompt olustur            │
│   2. llm.generate_vote_decision() → JSON yanit al               │
│   3. _parse_decision() → VoteDecision'a donustur                │
│   4. abstain_threshold kontrolu                                  │
├─────────────────────────────────────────────────────────────────┤
│ Cikis:                                                           │
│   └─ VoteDecision(choice, confidence, reasoning)                │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 Prompt Yapisi (prompts.py)

**Basit Format** (SharedLaw olmadan):
```
System: Sen bir blockchain yonetisim oylama asistanisin.
        Ilkelere gore analiz yap ve karar ver.

User: Fork Adi: Security-First Validator
      Oylama Stili: temkinli

      Ilkeler:
      - Ag guvenligini onceliklendir
      - Merkeziyetsizligi destekle

      Teklif:
      Baslik: [TEKLIF_BASLIGI]
      Aciklama: [TEKLIF_ACIKLAMASI]
```

**Gelismis Format** (SharedLaw ile):
```
System: Sen DAHAO yonetisim cercevesi icinde calisan bir oylama asistanisin.
        Kilit ilkeleri ASLA ihlal etme.

User: Fork Adi: Security-First Validator
      Miras Alinan: dahao-core v1.0.0

      KILIT ILKELER (ihlal edilemez):
      - @purpose_primacy: Tum kararlar belirtilen amaca hizmet etmeli
      - @democratic_evolution: Kolektif musavere ile evrilmeli
      - @transparency: Tum yonetisim halka acik olmali
      - @precautionary_default: Belirsizlikte korumaya meyil et
      - @protection_asymmetry: Koruma eklemek cikarmaktan kolay olmali
      - @inheritance_integrity: Alanlar kilit ilkeleri ihlal edemez

      YONETISIM ESIKLERI:
      - Ilke Degisikligi: %90 konsensus
      - Kural Ekleme: %75 konsensus
      - Koruma Carpani: 1.5x

      KULLANILAN TERIMLER:
      - @protection: [tanim]
      - @harm: [tanim]

      DOGRULAYICI ILKELERI:
      - Ag guvenligini onceliklendir (@precautionary_default ile uyumlu)
      - Merkeziyetsizligi destekle (@democratic_evolution ile uyumlu)

      TEKLIF:
      Baslik: [TEKLIF_BASLIGI]
      Aciklama: [TEKLIF_ACIKLAMASI]
```

### 3.3 LLM Yanit Semasi

```json
{
  "vote": "YES | NO | ABSTAIN | NO_WITH_VETO",
  "confidence": 0.0 - 1.0,
  "reasoning": "Neden bu karari verdigimin detayli aciklamasi..."
}
```

---

## 4. SharedLaw Yonetisim Cercevesi (data/)

### 4.1 Veri Dosyalari

| Dosya | Amac |
|-------|------|
| `terms.json` | Evrensel terimler sozlugu (@purpose, @vote, @evidence...) |
| `principles.json` | Temel ilkeler (6 kilitli, 3 acik) |
| `rules.json` | Yonetisim kurallari |
| `governance.json` | Konsensus esikleri, zamanlama ayarlari |
| `domains.json` | Alan kayit defteri |

### 4.2 Kilitli Ilkeler (Degistirilemez)

```
@purpose_primacy       → Tum kararlar belirtilen amaca hizmet etmeli
@democratic_evolution  → Kolektif musavere ile evrilmeli
@transparency          → Tum yonetisim halka acik olmali
@precautionary_default → Belirsizlikte korumaya meyil et
@protection_asymmetry  → Koruma eklemek cikarmaktan kolay olmali
@inheritance_integrity → Alt alanlar kilit ilkeleri ihlal edemez
```

### 4.3 SharedLaw Yukleme Akisi

```
SharedLaw.__init__(data_dir="data/")
         │
         ├─→ _load_terms() → terms.json → Dict[str, Term]
         │
         ├─→ _load_principles() → principles.json → Dict[str, Principle]
         │
         ├─→ _load_rules() → rules.json → Dict[str, Rule]
         │
         ├─→ _load_governance() → governance.json → Governance
         │
         └─→ _load_domains() → domains.json → DomainsRegistry
```

---

## 5. Fork Yapilandirmasi (config/fork.py)

### 5.1 Basit Format

```yaml
name: "Security-First Validator"
principles:
  - "Ag guvenligini onceliklendir"
  - "Merkeziyetsizligi destekle"
voting_style: "cautious"        # temkinli | dengeli | agresif
abstain_threshold: 0.6          # 0.6'dan dusuk guven = ABSTAIN
```

### 5.2 Gelismis Format (SharedLaw Referanslari ile)

```yaml
name: "Security-First Validator"
inherits: "dahao-core v1.0.0"
uses_terms:
  - "@protection"
  - "@harm"
  - "@evidence"
principles:
  - statement: "Ag guvenligini onceliklendir"
    aligns_with: "@precautionary_default"
  - statement: "Merkeziyetsizligi destekle"
    aligns_with: "@democratic_evolution"
voting_style: "cautious"
abstain_threshold: 0.6
persona: "Protokol dayanikliligi odakli guvenlik arastirmacisi"
```

### 5.3 Fork Dogrulama Akisi

```
Fork Dogrulama
      │
      ├─→ 1. Terim Referanslari Kontrolu
      │      uses_terms'deki tum @terimler SharedLaw'da mevcut mu?
      │
      ├─→ 2. Hizalama Kontrolu
      │      aligns_with'deki tum ilkeler SharedLaw'da mevcut mu?
      │
      └─→ 3. Kilit Ilke Ihlali Kontrolu
             Fork ilkeleri kilit ilkelerle catisiyor mu?

             ├─ Basit Dogrulama (--simple-validation)
             │  └─ Anahtar kelime eslemesi
             │
             └─ LLM Semantik Dogrulama (varsayilan)
                └─ Ollama ile anlam analizi
                   Ornek: "Hizi guvenlikten onceliklendir"
                         → @precautionary_default ihlali
```

---

## 6. Zincir Etkilesimi (chain/)

### 6.1 Teklif Sorgulama (governance.py)

```
fetch_voting_proposals()
         │
         ▼
┌─────────────────────────────────────────┐
│ 1. gRPC Sorgusu                          │
│    GovQueryStub.Proposals(               │
│      status=PROPOSAL_STATUS_VOTING_PERIOD│
│    )                                     │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 2. Protobuf Ayristirma                   │
│    Her proto_proposal icin:              │
│    ├─ ID cikart                          │
│    ├─ Any tipini unpack et               │
│    │   └─ TextProposal → baslik, aciklama│
│    ├─ Tarihleri al                       │
│    └─ Proposal objesi olustur            │
└────────────────────┬────────────────────┘
                     │
                     ▼
         List[Proposal] don
```

### 6.2 Oy Gonderme (governance.py)

```
submit_vote(proposal_id, choice, wallet)
         │
         ▼
┌─────────────────────────────────────────┐
│ 1. MsgVote Olustur                       │
│    ├─ proposal_id: int                   │
│    ├─ voter: cosmos1...                  │
│    └─ option: VOTE_OPTION_*              │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 2. Transaction Olustur                   │
│    tx = Transaction()                    │
│    tx.add_message(msg)                   │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 3. Gas ve Ucret Hesapla                  │
│    ledger.estimate_gas_and_fee_for_tx() │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 4. Imzala                                │
│    ├─ tx.seal() - Imza yapisi            │
│    ├─ tx.sign() - Ozel anahtar ile       │
│    └─ tx.complete() - Tamamla            │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 5. Yayinla ve Bekle                      │
│    ledger.broadcast_tx(tx)               │
│    tx.wait_to_complete()                 │
└─────────────────────────────────────────┘
```

---

## 7. Simulasyon Sistemi (simulation_swarm.py)

### 7.1 Ajan Personalari (Persona Tabanli)

Suru artik varsayilan olarak persona.json dosyalarini kullaniyor:

| Ajan | Persona Dosyasi | Arketip |
|------|-----------------|---------|
| Alice | `simulation/alice_persona.json` | Deep Ecologist |
| Bob | `simulation/bob_persona.json` | Rational Capitalist |
| Charlie | `simulation/charlie_persona.json` | Libertarian Decentralist |
| Dave | `simulation/dave_persona.json` | Institutional Conformist |
| Eve | `simulation/eve_persona.json` | Security Researcher |

**Not:** Kilit ilkeleri ihlal eden personalar (ornegin Bob'un "cevre pahasina kar") dogrulama basarisiz olur ve ajan baslamaz. Bu beklenen fail-fast davranisidir.

### 7.2 Suru Calistirma Akisi

```
python simulation_swarm.py
         │
         ▼
┌─────────────────────────────────────────┐
│ 1. On Kosul Kontrolu                     │
│    ├─ Ollama calisiyir mu?              │
│    └─ Zincir gRPC erisiliebilir mi?     │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 2. Cuzdan Yukleme                        │
│    simulation/wallets.yaml'dan          │
│    her ajan icin mnemonic yukle         │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 3. Ajanlari Baslat                       │
│    Her ajan icin (3 sn arayla):          │
│    ├─ Persona dosyasi (alice_persona.json)│
│    │   └─ LLM ile Fork'a donusturulur   │
│    ├─ Benzersiz cuzdan                   │
│    ├─ Benzersiz durum dosyasi            │
│    └─ subprocess.Popen(main.py           │
│         --persona simulation/X_persona.json│
│         --name X ...)                    │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│ 4. Cikti Izleme                          │
│    select.select() ile tum sureclerden   │
│    engelsiz okuma + renkli cikti         │
│    (Yesil=Alice, Sari=Bob, ...)         │
└─────────────────────────────────────────┘

# Test tekliflerini gonder
python submit_test_proposals.py

# Gercek zamanli izleme
streamlit run monitor.py
```

---

## 8. Denetim Gunlugu (decisions.log)

### 8.1 Kayit Formati

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "proposal_id": 42,
  "proposal_title": "Ag Guncelleme Teklifi",
  "fork_name": "Security-First Validator",
  "vote": "YES",
  "confidence": 0.85,
  "llm_reasoning": "Bu teklif ag guvenligini iyilestiriyor...",
  "reasoning_hash": "sha256:abc123...",
  "terms_referenced": ["@protection", "@stakeholder"],
  "principles_aligned": ["@precautionary_default"],
  "locked_constraints": ["@purpose_primacy", "@transparency"],
  "governance_version": "1.0.0"
}
```

### 8.2 Kullanim Amaci

- **Seffaflik**: Tum oylama kararlari halka acik
- **Denetlenebilirlik**: SHA256 hash ile dogrulanabilir
- **Proof of Alignment**: Gelecekte zincir uzerinde kanitlanabilir

---

## 9. Yapilandirma Dosyalari

### 9.1 config.yaml

```yaml
chain:
  chain_id: "dahao"
  grpc_url: "grpc+http://localhost:9090"
  fee_denom: "stake"
  address_prefix: "cosmos"
  gas_limit: 200000
  fee_amount: 1000

llm:
  model_name: "qwen3:14b"
  ollama_host: "http://localhost:11434"
  n_ctx: 8192

sidecar:
  poll_interval_seconds: 60
  max_retries: 3
  state_file: "sidecar_state.json"
  decisions_log: "decisions.log"
```

---

## 10. CLI Komutlari

### 10.1 Temel Kullanim

```bash
# Varsayilan ayarlarla calistir (fork.yaml kullanir)
python main.py

# Persona ile calistir (onerilen)
python main.py \
  --persona persona.json \
  --wallet "24 kelimelik mnemonic buraya" \
  --name Alice \
  --log-level DEBUG

# Persona ile onbellekleme (inceleme icin YAML kaydet)
python main.py \
  --persona persona.json \
  --persona-cache \
  --persona-cache-dir ./debug

# Fork dosyasi ile calistir (eski yontem)
python main.py \
  --fork simulation/alice.yaml \
  --wallet "24 kelimelik mnemonic buraya" \
  --state simulation/state_alice.json \
  --data-dir data/ \
  --name Alice \
  --log-level DEBUG

# Fork dogrulamayi atla
python main.py --skip-fork-validation

# Basit dogrulama kullan (LLM yerine)
python main.py --simple-validation
```

### 10.2 CLI Argumanlar Tablosu

| Arguman | Aciklama |
|---------|----------|
| `--persona` | persona.json dosya yolu (LLM ile Fork'a donusturulur) |
| `--persona-cache` | Persona-Fork eslemelerini onbelleklemeyi etkinlestir |
| `--persona-cache-dir` | Ozel onbellek dizini (varsayilan: ~/.cache/dahao/forks/) |
| `--fork` | fork.yaml dosya yolu (persona verilmezse kullanilir) |
| `--wallet` | 24 kelimelik mnemonic |
| `--state` | Durum dosyasi yolu |
| `--data-dir` | SharedLaw veri dizini |
| `--skip-fork-validation` | Fork dogrulamasini atla |
| `--simple-validation` | LLM yerine desen tabanli dogrulama |
| `--name` | Gunlukler icin ajan adi |
| `--log-level` | DEBUG, INFO, WARNING, ERROR |

### 10.3 Simulasyon Komutlari

```bash
# Tum ajanlari calistir
python simulation_swarm.py

# Sadece 3 ajan calistir
python simulation_swarm.py --agents 3

# 5 saniyelik baslama gecikisi
python simulation_swarm.py --delay 5.0

# On kontrolleri atla
python simulation_swarm.py --skip-checks
```

---

## 11. Hata Giderme

| Hata | Sebep | Cozum |
|------|-------|-------|
| "Failed to connect to Ollama" | Ollama calısmiyor | `ollama serve` calistir |
| "Model not found" | Model yuklenmemis | `ollama pull qwen3:14b` |
| "Failed to connect to chain" | Zincir gRPC erisilemsz | `ignite chain serve` calistir |
| "Invalid mnemonic" | Adres girilmis, mnemonic degil | 24 kelimelik ifade kullan |
| "Insufficient funds" | Cuzdan bakiyesi yetersiz | Cuzdan fonla |
| "Fork validation failed" | Fork kilit ilkeleri ihlal ediyor | fork.yaml'i duzelt veya `--skip-fork-validation` |
| "SharedLawLoadError" | data/*.json dosyalari eksik | data/ klasorunu kontrol et |
| "PersonaNotFoundError" | persona.json bulunamadi | Dosya yolunu kontrol et veya `--fork` kullan |
| "PersonaMappingError" | LLM persona esleme hatasi | LLM erisimini kontrol et, persona degerlerini incele |
| "Aligned principle '@protection' does not exist" | LLM terim kullanmis (ilke yerine) | Persona onbellegini temizle: `rm ~/.cache/dahao/forks/*.yaml` |
| "LLM used term '@xxx' in aligns_with" | Terim vs Ilke karisikligi | Mapper artik dogrulama yapiyor ve reddediyor |
| Persona kilit ilke dogrulamasini gecemiyor | Persona degerleri DAHAO cekirdegi ile catisiyor | Persona degerlerini ayarla veya fail-fast davranisini kabul et |

---

## 12. Ozet Akis Semas

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           DAHAO SIDECAR AKISI                            │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│   [BASLANGIC]                                                           │
│        │                                                                │
│        ▼                                                                │
│   ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌─────────┐          │
│   │ config  │     │ persona │     │  fork   │     │SharedLaw│          │
│   │  .yaml  │     │  .json  │     │  .yaml  │     │  data/  │          │
│   └────┬────┘     └────┬────┘     └────┬────┘     └────┬────┘          │
│        │               │               │               │                │
│        │               ▼               │               │                │
│        │    ┌─────────────────┐        │               │                │
│        │    │ Kimlik Adaptoru │        │               │                │
│        │    │ (LLM Donusumu)  │────────┼───────────────┤                │
│        │    └────────┬────────┘        │               │                │
│        │             │                 │               │                │
│        │             ▼                 │               │                │
│        │    ┌─────────────────┐        │               │                │
│        │    │      Fork       │◄───────┘               │                │
│        │    │   (oluşturulan) │                        │                │
│        │    └────────┬────────┘                        │                │
│        │             │                                 │                │
│        └─────────────┴─────────────────────────────────┘                │
│                      │                                                  │
│                      ▼                                                  │
│            ┌─────────────────┐                                          │
│            │  Fork Dogrulama │                                          │
│            │  (LLM/Pattern)  │                                          │
│            └────────┬────────┘                                          │
│                     │                                                   │
│                     ▼                                                   │
│   ┌─────────────────────────────────────────────────┐                  │
│   │              SIDECAR DONGUSU                     │                  │
│   │  ┌─────────────────────────────────────────┐    │                  │
│   │  │ 1. Teklifleri Getir (gRPC)               │    │                  │
│   │  │ 2. Her islenmemis teklif icin:           │    │                  │
│   │  │    a) LLM'den karar al                   │    │                  │
│   │  │    b) Karari kaydet (decisions.log)      │    │                  │
│   │  │    c) Oyu zincire gonder (MsgVote)       │    │                  │
│   │  │    d) Islenmis olarak isaretle           │    │                  │
│   │  │ 3. Bekle (poll_interval)                 │    │                  │
│   │  │ 4. Tekrarla                               │    │                  │
│   │  └─────────────────────────────────────────┘    │                  │
│   └─────────────────────────────────────────────────┘                  │
│                       │                                                 │
│                       ▼                                                 │
│   ┌─────────────────────────────────────────────────┐                  │
│   │                  CIKTILAR                        │                  │
│   │  ├─ decisions.log: Denetim kayitlari            │                  │
│   │  ├─ sidecar_state.json: Islenmis teklifler      │                  │
│   │  ├─ ~/.cache/dahao/forks/: Onbellekli Fork'lar  │                  │
│   │  └─ Zincir: MsgVote islemleri                   │                  │
│   └─────────────────────────────────────────────────┘                  │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 13. Tamamlanan Ozellikler

- **Kimlik Adaptoru**: Harici persona.json dosyalarini Fork'a donusturme (LLM tabanli)
- **Persona Onbellekleme**: Derlenmis Fork'lari YAML olarak kaydetme
- **Gercek Zamanli Izleme**: Streamlit tabanli karar izleme panosu (monitor.py)
- **Test Teklif Sistemi**: Otomatik test teklifi gonderme (submit_test_proposals.py)
- **Terim vs Ilke Dogrulamasi**: aligns_with alaninda terim kullanimi engellendi

## 14. Gelecek Gelistirmeler

- **IPFS Sync**: SharedLaw guncellemelerini IPFS uzerinden cekme
- **Proof of Alignment**: Oylama gerekceleri zincir uzerinde kanitlanabilir
- **Multi-chain Support**: Birden fazla Cosmos zincirine baglanti
- **Plugin System**: Ozel karar mekanizmalari ekleme

---

*Bu dokuman Leviathan/DAHAO sidecar projesinin tam teknik akisini aciklar. Guncel kalması icin kod degisiklikleri sonrasi guncellenmeli.*
