---
name: aruba-cloud
description: Gestisci risorse Aruba Cloud CMP con CLI e SDK Go ufficiali; crea inventari, report Markdown e confronti tra scansioni. Verifica la compatibilità per VPS delle piattaforme precedenti. Non riguarda HPE Aruba Networking.
---

# Aruba Cloud

Usa la CLI ufficiale inclusa in `bin/acloud` per le operazioni correnti; usa lo SDK Go per integrazioni applicative o funzioni non esposte dalla CLI. Risolvi i percorsi rispetto alla directory della skill, indipendentemente dalla cartella di lavoro.

Per report o confronti da file JSON già disponibili usa direttamente `scripts/reports.py`: funziona offline con la sola libreria standard Python, senza configurare account o installare la CLI.

## Verifica iniziale per operazioni CMP

Esegui `python3 scripts/inventory.py doctor`: verifica versione, integrità del binario e presenza della configurazione senza visualizzare credenziali né chiamare API. Se manca il binario, esegui `python3 scripts/install_cli.py`: scarica una release ufficiale fissata e ne verifica il checksum. Sono supportati macOS e Linux, arm64 e amd64; il test locale completo è stato eseguito su macOS arm64.

Leggi [references/operations.md](references/operations.md) per autenticazione, comandi e limiti. Prima di un'operazione consulta `bin/acloud <dominio> <risorsa> <azione> --help`: non dedurre flag da altre versioni.

Identifica account/profilo e progetto. Passa `--profile` quando usi più account e `--project-id` esplicito alle risorse del progetto. I contesti CLI salvano progetti e possono restare associati a un altro account: non cambiare un contesto globale per una singola operazione. Le variabili delle credenziali prevalgono anche sul profilo: verifica gli override senza mostrarne i valori.

## Inventario

`python3 scripts/inventory.py inventory --profile NOME --account-label ETICHETTA --output /percorso/privato/inventario.json`

Ometti `--profile` solo se il profilo attivo è quello voluto. Usa `--project-id ID` per restringere il progetto e `--kinds servers,volumes,vpcs` per selezionare le famiglie. L'helper esegue solo liste, pagina i risultati e scrive un file nuovo con permessi 0600. Gli errori sono separati dai risultati vuoti: `complete=false` e codice di uscita 2 indicano una raccolta incompleta. La completezza si riferisce solo alle famiglie selezionate; non comprende tutti i servizi Aruba, il billing o le piattaforme precedenti. La scansione non è uno snapshot atomico: variazioni durante il paging possono renderla incompleta.

Il report contiene metadati di infrastruttura; mantienilo locale. L'helper non restituisce corpi degli errori né token. Non usare `--debug` con credenziali reali: la CLI avvisa che può esporre segreti negli header.

Presenta il risultato con un breve riepilogo per progetto e famiglia, indicando ambito selezionato, completezza ed eventuali codici diagnostici. Mantieni distinti conteggi verificati e dati non accessibili; non ricavare costi o risorse inutilizzate dal solo inventario. Fornisci il percorso del report privato per approfondire.

Se l'utente vuole provare il flusso senza un account, gli esempi in `examples/before.json` e `examples/after.json` funzionano con i comandi offline. Con la CLI già installata, `python3 scripts/demo.py` esegue due scansioni reali contro un server locale sintetico e genera entrambi i report. `--output-dir NUOVA_DIRECTORY` conserva i risultati dimostrativi. Dichiara che sono dati sintetici e che non verificano autenticazione o compatibilità con Aruba in produzione.

## Report e confronto offline

Leggi [references/reports.md](references/reports.md) per formato, semantica del confronto e codici diagnostici.

`python3 scripts/reports.py render /percorso/inventario.json --output /percorso/privato/report.md`

`python3 scripts/reports.py diff /percorso/prima.json /percorso/dopo.json --output /percorso/privato/modifiche.md`

Per confronti futuri registra una `--account-label` stabile e non segreta dopo aver identificato l'account voluto. È un'etichetta dell'operatore, non un ID autenticato; il nome del profilo e gli hash degli endpoint non provano l'identità dell'account. Riusa la stessa etichetta solo nello stesso account. Le raccolte devono avere uguale ambito, fonte e configurazione compatibile, con finestre temporali successive. I report versione 1 sono leggibili ma privi dell'ambito necessario al confronto; raccogli nuovi inventari etichettati. Mantieni i metadati originali in caso di rifiuto per ambito incompatibile.

Il confronto abbina ID di progetto, famiglia e risorsa e mostra i percorsi dei campi modificati. Una famiglia incompleta resta non confrontabile; le altre possono essere confrontate. Progetti assenti indicano variazioni di visibilità, senza classificare automaticamente le loro risorse come create o cancellate. Tratta aggiunte e rimozioni come differenze osservate, non prova di azioni sul cloud. File Markdown nuovi: permessi 0600, nessuna sovrascrittura. Codice 2 con file prodotto significa risultato parziale; un input incompatibile o invalido produce solo un codice diagnostico.

## Modifiche alle risorse

Installare la skill non autorizza modifiche al cloud. Esegui le modifiche richieste dall'utente nello scopo già autorizzato, senza una seconda conferma. Per risorse con costo, cancellazioni, spegnimenti o variazioni di rete, identifica account, progetto, ID, dipendenze ed effetto atteso prima dell'esecuzione; chiedi chiarimenti solo se dati o autorizzazione mancano.

Non accendere, spegnere, creare o cancellare risorse per collaudare la connessione. Rispetta i vincoli già stabiliti per ogni server. Per cancellazioni autorizzate usa `delete --dry-run` se disponibile, poi l'azione sullo stesso ID; `--yes` può evitare il prompt duplicato della CLI. Dopo una modifica rileggi lo stato con `get`; una risposta accettata non prova il completamento. Usa polling limitato nel tempo e uno stato finale specifico. Non ritentare una creazione con esito incerto: riconcilia prima con una lettura per evitare duplicati e addebiti.

## SDK Go

Per implementare integrazioni leggi [references/sdk.md](references/sdk.md). Le istruzioni del repository corrente possono differire dalla versione incorporata nella CLI: verifica le API nella dipendenza effettiva. Versioni e origine del binario incluso sono in [references/provenance.json](references/provenance.json).

## Verifica e aggiornamento

I test locali si eseguono con `python3 scripts/test_inventory.py` e `python3 scripts/test_reports.py`; usano fixture locali e file sintetici, senza contattare Aruba. Ripeti quelli pertinenti dopo modifiche a CLI, helper o report. La versione della CLI è fissata nel manifest; non aggiornarla silenziosamente.
