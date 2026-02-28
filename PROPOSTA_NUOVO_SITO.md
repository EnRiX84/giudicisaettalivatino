# Proposta di Adozione del Nuovo Sito Web Istituzionale

**IISS "Giudici Saetta e Livatino" - Ravanusa e Campobello di Licata**
**Documento per il Team Digitale** | Febbraio 2026

---

## 1. Introduzione

Il presente documento illustra la proposta di sostituzione dell'attuale sito web istituzionale, basato su Joomla CMS con template JSN Pixel 2 (risalente ai primi anni 2010), con un nuovo sito statico costruito con tecnologie moderne (HTML5, CSS3, JavaScript). L'obiettivo e' offrire all'utenza scolastica un'esperienza di navigazione contemporanea, sicura e performante, in linea con le Linee Guida AgID per i siti web della Pubblica Amministrazione.

---

## 2. Confronto: Sito Attuale vs Nuovo Sito

| Aspetto | Sito Attuale (Joomla) | Nuovo Sito (Statico) |
|---|---|---|
| **Design e UX** | Template JSN Pixel 2 datato, estetica piatta anni 2010, non coerente con l'identita' visiva della scuola | Design moderno e curato, approccio mobile-first, palette istituzionale blu/oro, tipografia professionale |
| **Navigazione** | Menu confuso con voci ridondanti, dropdown non funzionanti su dispositivi mobili | Navbar sticky con hamburger menu responsive, dropdown ben organizzati, struttura logica e intuitiva |
| **Performance** | Joomla appesantito da numerosi plugin, query al database, caricamento lento (3-6 secondi) | Sito statico ultra-veloce, nessun database, caricamento quasi istantaneo (<1 secondo) |
| **Sicurezza** | Richiede aggiornamenti costanti di Joomla, plugin e PHP; vulnerabilita' note e frequenti | Sito statico = zero vulnerabilita' server-side, nessun pannello di amministrazione esposto |
| **Manutenzione** | Server PHP + MySQL, aggiornamenti CMS e plugin, gestione hosting complessa | Hosting statico gratuito o a costo minimo, zero manutenzione server, aggiornamenti tramite semplice upload di file |
| **Contenuti** | Documenti difficili da reperire, notizie in elenco verticale poco leggibile | Card grid per avvisi e notizie, toggle mostra/nascondi, sezioni tematiche ben organizzate |
| **Esperienza Mobile** | Non responsive: il sito risulta inutilizzabile su smartphone | Mobile-first: navigazione perfetta su smartphone e tablet, elementi touch-friendly |
| **Accessibilita'** | Carente, non conforme ai requisiti AgID | HTML5 semantico, contrasti adeguati (WCAG), navigazione da tastiera, struttura accessibile |

---

## 3. Funzionalita' del Nuovo Sito

Il nuovo sito e' stato progettato per coprire tutte le esigenze informative della comunita' scolastica:

- **24 pagine interne** con contenuti completi e aggiornati (organigramma, regolamenti, modulistica, contatti, sedi, ecc.)
- **23 avvisi e notizie** organizzati in card con layout a griglia, facilmente consultabili e filtrabili
- **Offerta formativa** con schede dedicate per i 4 indirizzi di studio attivi
- **Sezione progetti** strutturata: Erasmus+, PNRR, PON FESR, PCTO, e altri progetti attivi
- **15 banner istituzionali** per link rapidi a piattaforme ministeriali e servizi (Registro Elettronico, Segreteria Digitale, PAGO IN RETE, ecc.)
- **Anno scolastico auto-aggiornante** tramite JavaScript, senza intervento manuale
- **Pannello di gestione notizie integrato** (`admin.html`): la segreteria inserisce le notizie tramite un'interfaccia web semplice (titolo, categoria, data, descrizione, allegati), clicca "Pubblica" e le modifiche sono online istantaneamente. Nessuna competenza tecnica richiesta
- **Backup automatico** ad ogni salvataggio: il sistema crea una copia di sicurezza prima di ogni modifica
- **Tutti i link a documenti PDF verificati** e funzionanti
- **Server locale leggero**: avvio con doppio click su un file `.bat`, senza installazioni aggiuntive

---

## 4. Deploy e Infrastruttura

### Confronto deploy

| Aspetto | Sito Attuale (Joomla) | Nuovo Sito |
|---|---|---|
| **Requisiti server** | PHP 7+, MySQL, moduli Apache/Nginx, certificato SSL, cPanel | Qualsiasi web server statico (anche il server esistente) |
| **Aggiornamento contenuti** | Accesso a pannello Joomla, rischio di rotture dopo aggiornamento plugin | Interfaccia admin dedicata, un click per pubblicare |
| **Backup** | Backup database + file system, procedure complesse | Singola cartella di file, copiabile su chiavetta USB |
| **Migrazione** | Esportazione database, compatibilita' versioni PHP, riconfigurazione | Copia della cartella del sito, funziona ovunque |
| **Tempo di deploy** | Ore (installazione CMS, configurazione, import dati) | Minuti (upload cartella via FTP o cPanel file manager) |

### Come si effettua il deploy

Il nuovo sito puo' essere pubblicato **sullo stesso hosting attuale** senza modifiche infrastrutturali:

1. **Upload dei file** nella document root del server (stessa cartella dove risiede Joomla attualmente)
2. Non servono database, PHP o configurazioni speciali
3. Il sito funziona immediatamente

In alternativa, si puo' ospitare **gratuitamente** su GitHub Pages, Netlify o Cloudflare Pages, eliminando del tutto i costi di hosting.

### Gestione quotidiana da parte della segreteria

1. La segretaria fa doppio click su **"Avvia Gestione Sito.bat"**
2. Si apre automaticamente il browser con il pannello di gestione
3. Compila il form per aggiungere notizie, riordina o elimina quelle vecchie
4. Clicca **"Pubblica sul sito"** — fatto, le notizie sono online
5. Se il sito e' su hosting remoto, l'upload della cartella `data/` aggiorna le notizie

---

## 5. Vantaggi Economici

| Voce di costo | Sito Joomla (stima annua) | Nuovo Sito Statico |
|---|---|---|
| Hosting web | 50 - 150 euro/anno (PHP + MySQL) | **Gratuito** (GitHub Pages, Netlify, Cloudflare Pages) |
| Manutenzione CMS | Tempo-uomo per aggiornamenti e backup | **Zero**: nessun CMS da aggiornare |
| Licenze software / template | Variabile | **Nessuna**: codice interamente proprietario |
| Interventi tecnici di emergenza | Frequenti (problemi plugin, incompatibilita') | **Rari**: struttura semplice e stabile |
| **Costo totale stimato** | **100 - 300+ euro/anno** + tempo | **0 euro/anno** |

L'adozione del sito statico elimina completamente i costi ricorrenti di hosting e manutenzione, liberando risorse economiche e di tempo per il personale scolastico.

---

## 6. Conclusioni

Il nuovo sito web rappresenta un significativo passo avanti rispetto alla soluzione attuale sotto ogni aspetto: design, usabilita', performance, sicurezza e sostenibilita' economica. La migrazione a un sito statico moderno garantisce:

- **Esperienza utente superiore** per famiglie, studenti e personale, anche da dispositivi mobili
- **Azzeramento dei costi** di hosting e manutenzione
- **Sicurezza intrinseca** senza necessita' di aggiornamenti continui
- **Conformita'** alle indicazioni AgID in materia di accessibilita' e usabilita'
- **Autonomia gestionale** per il team digitale nella pubblicazione dei contenuti

Si sottopone pertanto la presente proposta all'approvazione del Team Digitale per procedere alla pubblicazione del nuovo sito istituzionale.

---

*Documento redatto per il Team Digitale - IISS "Giudici Saetta e Livatino"*
*Ravanusa e Campobello di Licata (AG)*
