# Administratörsguide — Bonuscard

Den här guiden är för **Bonuscard-administratörer** (managers) som
konfigurerar anslutning, produktkatalog och kundkopplingar. Kassörer använder
en separat guide: [Kassa-guide](pos-kassor.md).

English version: [Manager guide](../en/pos-manager.md)

## Innan du börjar

- Din användare tillhör gruppen **Bonuscard Manager** (eller är administratör).
- Du har Bonuscard API-basadress och inloggningsuppgifter för ditt bolag.

## 1. Öppna Bonuscard-anslutningar

1. Öppna appswitchern och välj **Bonuscard**.
2. Du kommer till **Anslutningar**.

![Lista över Bonuscard-anslutningar](../images/pos-manager/01-bonuscard-connections-list.png)

Skapa en anslutning med **Ny**, eller öppna en befintlig rad för att redigera.

## 2. Konfigurera och testa anslutningen

På anslutningsformuläret anger du minst:

| Fält | Syfte |
|------|--------|
| **API-basadress** | Bonuscard API-rot (produktion eller test). |
| **API-användarnamn** / **API-lösenord** | Basic-auth-uppgifter. |
| **API-kultur** | Språk/kultur som skickas till API:t. |
| **Använd för Bonuscard API** | Markera anslutningen som bolaget ska använda. |
| **Aktiv** | Anslutningen är tillgänglig. |

Klicka sedan på **Testa anslutning**. Status ska bli **OK** när URL och
uppgifter är giltiga.

![Anslutningsformulär med Testa anslutning](../images/pos-manager/02-connection-form.png)

På samma formulär finns också:

- **Kör massförladdning** / **Uppdatera massförladdning** — förladdar
  partnerkopplingar (färre live-sökningar i kassan).
- **Kör katalogkontroll** — kontrollerar produkter som fortfarande är
  **Ej angiven** mot Bonuscard (endast managers).

## 3. Massförladdning och katalogkontroll (valfritt)

Scrolla formuläret till **Massförladdning** och katalogkontroll.

![Inställningar för massförladdning och katalogkontroll](../images/pos-manager/03-connection-bulk-catalog.png)

Vanliga alternativ:

- **Aktivera massförladdning av partners** — dagligt jobb för partners som
  aldrig skannats.
- **TTL (timmar)** / **batchstorlek** — hur ofta och hur många partners per körning.
- **Aktivera katalogkontroll** — schemalagd kontroll av produkter med status
  **Ej angiven** (kräver **Katalogkontrollkund**).

## 4. Markera produkter i Bonuscard-katalogen

Endast produkter markerade **I Bonuscard-katalog** (med streckkod eller intern
referens) skickas till Bonuscard från kassan.

1. Gå till **Lager → Produkter → Produkter**.
2. Byt till **listvy** om det behövs.

![Produktlista](../images/pos-manager/04-products-list.png)

3. Markera en eller flera produkter.
4. Öppna **Åtgärder** och välj:

   - **Markera som Bonuscard-katalog**
   - **Markera som ej i Bonuscard-katalog**
   - **Återställ Bonuscard-katalogstatus**
   - **Kontrollera Bonuscard-katalog** (proben för valda produkter)

![Produktåtgärder med Bonuscard-katalog](../images/pos-manager/05-products-catalog-actions.png)

Produkter utan streckkod eller artikelnummer kan inte markeras som i katalog.

I kassan visas produkter markerade **I Bonuscard-katalog** med ett rosa
Bonuscard-märke på produktbrickan (kassörer använder det för att se vilka
rader som går till Bonuscard).

## 5. Granska kundens Bonuscard-status

1. Öppna **Fakturering → Kunder → Kunder** (eller Kontakter, om installerat).

![Kundlista](../images/pos-manager/07-customers-list.png)

2. Öppna en kund. Formuläret visar en **Bonuscard**-smartknapp (t.ex.
   **Linked**) och fliken **Bonuscard**.

![Kundformulär med Bonuscard-knapp och flik](../images/pos-manager/08-partner-form.png)

3. På fliken **Bonuscard** kan du:

   - Se status, värvningskod, senaste synk och anteckningar
   - **Kontrollera Bonuscard** — tvinga en ny uppslagning
   - **Återställ Bonuscard-status** — rensa kopplingen
   - **Registrera till Bonuscard** — när status är **not_found** (telefon krävs)

![Partnerfliken Bonuscard](../images/pos-manager/09-partner-bonuscard-tab.png)

## 6. Kassarabattprodukt

I **Kassa → Konfiguration → Inställningar**, ange en **Rabattprodukt**.
Bonuscard-rabatter som inte kan läggas som radprocent använder den produkten.
Kassörer kan inte åtgärda detta från kassan.

## Snabbchecklista

1. Anslutning konfigurerad, **Använd för Bonuscard API** markerad, **Testa anslutning** = OK.
2. Katalogprodukter markerade (och kontrollerade om ni använder katalogkontroll).
3. Viktiga kunder kopplade (eller massförladdning aktiverad).
4. Kassarabattprodukt konfigurerad.
5. Ge kassörerna [kassa-guiden](pos-kassor.md).

## Behöver du mer hjälp?

- Fullständig konfiguration: [modul-README](../../../bonuscard_odoo/README.rst)
- Teknisk POS-flödesbeskrivning: [POS-integration](../../bonuscard_pos_integration_explanation.md)
