# Kassa-guide — Bonuscard

Den här guiden är för kassörer som säljer i **Kassa (Point of Sale)**. Den
beskriver hur du hittar Bonuscard-kunder, registrerar nya medlemmar, anger
rabattkoder och slutför ett köp så att lojalitetsrabatter fungerar.

English version: [POS cashier guide](../en/pos-cashier.md)

## Innan du börjar

- Du är redan på kassans produktskärm (kassan är öppen).
- En administratör måste redan ha konfigurerat Bonuscard-anslutningen och
  markerat vilka produkter som ingår i Bonuscard-katalogen. Endast
  katalogprodukter ingår i Bonuscard-rabatter och poäng; övriga produkter
  säljs som vanligt. På produktskärmen visas katalogprodukter med ett rosa
  Bonuscard-märke i övre vänstra hörnet.

![Kassans produktskärm](../images/pos-cashier/03-pos-product-screen.png)

## 1. Hitta och välj en Bonuscard-kund

Koppla alltid en kund till ordern innan du förväntar dig Bonuscard-rabatter.

1. Klicka på **Kund** längst ner i orderpanelen.
2. Sök på namn, telefon, e-post eller **Bonuscard-värvningskod**.

![Kundlista med Bonuscard-märken](../images/pos-cashier/04-customer-list.png)

### Statusmärken

| Märke | Betydelse |
|-------|-----------|
| **Bonuscard** (grönt) | Kunden är kopplad — rabatter och validering kan köras. |
| **Ingen Bonuscard** (grått) | Ingen matchande Bonuscard-medlem hittades. |
| **Flera träffar** (gult) | Bonuscard hittade flera träffar — be en administratör åtgärda kopplingen. |

### Söktips

Skriv ett telefonnummer (eller värvningskod / e-post) i **Sök kunder…**.
Om kunden inte finns lokalt, tryck **Enter** — kassan kan söka i Bonuscard
och importera en exakt träff.

![Sök kund på telefonnummer](../images/pos-cashier/09-customer-search-phone.png)

3. Tryck på kundraden för att välja. Orderpanelen visar namnet i stället för
   **Kund**.

![Kopplad kund vald på ordern](../images/pos-cashier/06-customer-selected-linked.png)

Du kan få ett kort meddelande när en kopplad medlem upptäcks.

## 2. Registrera en kund utan Bonuscard

Om märket är **Ingen Bonuscard** och kunden vill bli medlem:

1. Öppna kundlistan.
2. Öppna menyn **⋮** på kundens rad.
3. Välj **Registrera med Bonuscard**.

![Registrera med Bonuscard i partnermenyn](../images/pos-cashier/05-register-with-bonuscard-menu.png)

Kunden **måste ha ett telefonnummer**. Vid lyckad registrering får du en
bekräftelse och statusen blir kopplad. Om det misslyckas, läs aviseringen
(t.ex. saknat telefonnummer) och komplettera kontaktuppgifterna.

## 3. Sälj produkter

Lägg till produkter som vanligt. Bonuscard utvärderar bara rader som är
markerade **I Bonuscard-katalog** av en administratör (och som har
streckkod eller intern referens).

### Hitta katalogprodukter i rutnätet

På produktbrickorna visas katalogprodukter med ett litet **rosa
Bonuscard-märke** (B) i **övre vänstra** hörnet. Produkter utan det märket
skickas inte till Bonuscard (status **Ej angivet** eller **Ej i
Bonuscard-katalog**).

Tryck länge på en produktbricka för att öppna **Produktinfo** — där visas
också Bonuscard-katalogstatus för produkter med en variant.

- Katalogprodukter (märke synligt): Bonuscard kan tillämpa rabatter eller
  samla förmåner automatiskt när kunden är kopplad.
- Övriga produkter (inget märke): säljs som vanligt; ignoreras av Bonuscard.

Om en rabatt tillämpas visas en bekräftelse och ordersumman uppdateras.
Varaktiga varningar stannar tills du stänger dem — läs dem om något
misslyckats.

![Order med en produktrad](../images/pos-cashier/10-product-added-order.png)

## 4. Ange en Bonuscard-rabattkod

Använd detta när kunden har en kod (kupong / kampanjkod) att aktivera.

1. Se till att en kund är vald på ordern.
2. Klicka på **⋮** (Åtgärder) bredvid **Anteckning**.
3. I dialogrutan **Åtgärder**, klicka på **Bonuscard**.

![Åtgärder-dialog med Bonuscard-knapp](../images/pos-cashier/07-actions-menu-bonuscard.png)

4. Ange koden och klicka på **Tillämpa** (Apply).

![Dialog Bonuscard-rabattkod](../images/pos-cashier/08-discount-code-popup.png)

Vad som händer sedan:

- **Lyckades** — koden aktiveras och varukorgen kontrolleras om för rabatter.
- **Vissa koder** kan inte förregistreras; kassan skickar dem ändå vid
  köpvalidering (du kanske inte får ett separat meddelande för den vägen).
- **Fel** (fel kod, ingen kund, m.m.) visas som varaktiga felaviseringar
  tills du stänger dem.

## 5. Ta betalt

Klicka på **Betalning** och slutför försäljningen som vanligt.

I bakgrunden slutför Bonuscard köpet när den betalda ordern synkas. Du
behöver inget separat Bonuscard-steg.

Om slutförandet misslyckas kan du se en varaktig varning. Kontakta en
administratör — kundens Bonuscard-session kan behöva återställas.

## 6. Avbryta eller ändra ordern

Följande åtgärder kan avbryta ett pågående Bonuscard-köp så att kunden inte
låses kvar:

- Ta bort ordern eller starta en ny
- Stänga kassan
- Byta kund (avbrott körs först; om avbrottet misslyckas blockeras
  kundbytet)

Om du får en varning om att avbrottet misslyckades, tvinga **inte** fram
ett nytt köp för samma medlem förrän en administratör har rensat det — eller
vänta tills låsningen går ut.

## Snabbchecklista

1. Välj (eller registrera) kunden — leta efter det gröna märket **Bonuscard**.
2. Lägg till katalogprodukter (rosa **B**-märke på brickan); håll utkik efter
   automatiska rabatter.
3. Valfritt: **Åtgärder → Bonuscard** för en rabattkod.
4. Ta betalt som vanligt.
5. Stäng och åtgärda eventuella varaktiga Bonuscard-varningar.

## Behöver du mer hjälp?

- Konfiguration och katalog: [modul-README](../../../bonuscard_odoo/README.rst)
- Teknisk POS-flödesbeskrivning: [POS-integration](../../bonuscard_pos_integration_explanation.md)
