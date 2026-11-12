---
name: aruba-cloud
description: Gestisci risorse Aruba Cloud CMP con CLI e SDK Go ufficiali per inventario, server, rete, storage, database e Kubernetes. Verifica la compatibilità prima di operare su VPS delle piattaforme precedenti. Non riguarda HPE Aruba Networking.
---

# Aruba Cloud

Usa la CLI ufficiale inclusa in `bin/acloud` per le operazioni correnti; usa lo SDK Go per integrazioni applicative o funzioni non esposte dalla CLI. Risolvi i percorsi rispetto alla directory della skill, indipendentemente dalla cartella di lavoro.

## Verifica iniziale

Esegui `python3 scripts/inventory.py doctor`: verifica versione, integrità del binario e presenza della configurazione senza visualizzare credenziali né chiamare API. Se manca il binario, esegui `python3 scripts/install_cli.py`: scarica una release ufficiale fissata e ne verifica il checksum. Sono supportati macOS e Linux, arm64 e amd64; il test locale completo è stato eseguito su macOS arm64.

Leggi [references/operations.md](references/operations.md) per autenticazione, comandi e limiti. Prima di un'operazione consulta `bin/acloud <dominio> <risorsa> <azione> --help`: non dedurre flag da altre versioni.

Identifica account/profilo e progetto. Passa `--profile` quando usi più account e `--project-id` esplicito alle risorse del progetto. I contesti CLI salvano progetti e possono restare associati a un altro account: non cambiare un contesto globale per una singola operazione. Le variabili delle credenziali prevalgono anche sul profilo: verifica gli override senza mostrarne i valori.

## Inventario

`python3 scripts/inventory.py inventory --profile NOME --output /percorso/privato/inventario.json`

Ometti `--profile` solo se il profilo attivo è quello voluto. Usa `--project-id ID` per restringere il progetto e `--kinds servers,volumes,vpcs` per selezionare le famiglie. L'helper esegue solo liste, pagina i risultati e scrive un file nuovo con permessi 0600. Gli errori sono separati dai risultati vuoti: `complete=false` e codice di uscita 2 indicano una raccolta incompleta. La completezza si riferisce solo alle famiglie selezionate; non comprende tutti i servizi Aruba, il billing o le piattaforme precedenti. La scansione non è uno snapshot atomico: variazioni durante il paging possono renderla incompleta.

Il report contiene metadati di infrastruttura; mantienilo locale. L'helper non restituisce corpi degli errori né token. Non usare `--debug` con credenziali reali: la CLI avvisa che può esporre segreti negli header.

Presenta il risultato con un breve riepilogo per progetto e famiglia, indicando ambito selezionato, completezza ed eventuali codici diagnostici. Mantieni distinti conteggi verificati e dati non accessibili; non ricavare costi o risorse inutilizzate dal solo inventario. Fornisci il percorso del report privato per approfondire.

Se l'utente vuole provare il flusso senza un account, esegui `python3 scripts/demo.py`: usa CLI e helper reali contro un server locale con dati sintetici e configurazione temporanea. Dichiara che è una dimostrazione e che non verifica autenticazione o compatibilità con Aruba in produzione.

## Modifiche alle risorse

Installare la skill non autorizza modifiche al cloud. Esegui le modifiche richieste dall'utente nello scopo già autorizzato, senza una seconda conferma. Per risorse con costo, cancellazioni, spegnimenti o variazioni di rete, identifica account, progetto, ID, dipendenze ed effetto atteso prima dell'esecuzione; chiedi chiarimenti solo se dati o autorizzazione mancano.

Non accendere, spegnere, creare o cancellare risorse per collaudare la connessione. Rispetta i vincoli già stabiliti per ogni server. Per cancellazioni autorizzate usa `delete --dry-run` se disponibile, poi l'azione sullo stesso ID; `--yes` può evitare il prompt duplicato della CLI. Dopo una modifica rileggi lo stato con `get`; una risposta accettata non prova il completamento. Usa polling limitato nel tempo e uno stato finale specifico. Non ritentare una creazione con esito incerto: riconcilia prima con una lettura per evitare duplicati e addebiti.

## SDK Go

Per implementare integrazioni leggi [references/sdk.md](references/sdk.md). Le istruzioni del repository corrente possono differire dalla versione incorporata nella CLI: verifica le API nella dipendenza effettiva. Versioni e origine del binario incluso sono in [references/provenance.json](references/provenance.json).

## Verifica e aggiornamento

I test locali si eseguono con `python3 scripts/test_inventory.py`; usano credenziali fittizie e un server HTTP locale. Non contattano Aruba. Ripetili dopo aggiornamenti alla CLI o all'helper. La versione della CLI è fissata nel manifest; non aggiornarla silenziosamente.
