# CLI ufficiale e autenticazione

CLI: acloud 1.0.0, basata su sdk-go v1.0.4. L'installer supporta macOS e Linux arm64/amd64 e verifica checksum fissati; i test locali iniziali sono stati eseguiti su macOS arm64. Non richiede Go installato. Il binario proviene dalla release ufficiale con SHA-256 verificato; la verifica non equivale a una firma indipendente del produttore.

## Credenziali

La nuova CMP usa OAuth2 client credentials. Credenziali SSH e accesso al pannello non sono una coppia client ID/client secret.

Nel portale https://my.arubacloud.com apri UTILITIES > Developer Tools > Client Credentials > Create Client Credential. Il secret viene mostrato solo durante la creazione: salvalo in un gestore di password. Fonte: https://kb.arubacloud.com/en/utilities/api/client-credentials/creating.aspx

Configura localmente in un terminale interattivo, sostituendo il client ID:

```sh
/percorso/skill/bin/acloud config profile set personale --client-id CLIENT_ID
```

La CLI richiede il secret con input nascosto. Non usare `--client-secret`, non incollare secret nella chat né inserirli in script o nella cronologia shell. La configurazione è YAML con secret in chiaro protetto da permessi 0600: `$XDG_CONFIG_HOME/acloud/config.yaml`, oppure `~/.config/acloud/config.yaml`. In alternativa un secret manager può fornire `ACLOUD_CLIENT_ID` e `ACLOUD_CLIENT_SECRET` nel solo ambiente del processo. Non stampare l'intera configurazione per diagnostica. `config show` maschera il secret ma rivela il client ID.

Selezione del profilo: `--profile`, `ACLOUD_PROFILE`, profilo attivo salvato. Le variabili `ACLOUD_CLIENT_ID` e `ACLOUD_CLIENT_SECRET` prevalgono sul file anche scegliendo un profilo: prima di cambiare account verifica la presenza di override senza mostrarne il valore.

Produzione: `https://api.arubacloud.com`; issuer configurato dalla CLI/SDK. Non cambiare `ACLOUD_BASE_URL` o `ACLOUD_TOKEN_ISSUER_URL` con credenziali reali senza verificarne la destinazione.

## Operazioni

Sostituisci `acloud` con il percorso assoluto della CLI inclusa nella skill.

```sh
acloud --profile personale management project list -o json
acloud --profile personale compute cloudserver list --project-id ID -o json
acloud --profile personale compute cloudserver get SERVER_ID --project-id ID -o json
acloud --profile personale network vpc list --project-id ID -o json
acloud --profile personale storage blockstorage list --project-id ID -o json
acloud --profile personale database dbaas list --project-id ID -o json
acloud --profile personale container kaas list --project-id ID -o json
```

Le liste espongono `--limit` e `--offset`; una pagina non è un inventario completo. Alcune liste vuote producono testo anche con `-o json`: l'helper gestisce solo i messaggi noti della versione inclusa e rifiuta risposte inattese.

Altri comandi: snapshot e backup di volumi, subnet e security group, Elastic IP e load balancer, peering e VPN, container registry, chiavi, KMS e job. Alcuni richiedono un oggetto padre oltre al progetto: consulta l'help. La disponibilità di un comando non prova che il servizio sia attivo o autorizzato sull'account.

`power-on` e `power-off` operano sui cloud server. Creazione, modifica e cancellazione dipendono dall'autorizzazione corrente. Dopo l'azione controlla `get` fino allo stato atteso, con un limite temporale.

## Limiti e aggiornamenti

L'helper inventaria progetti e sette famiglie: server, volumi, VPC, Elastic IP, DBaaS, Kubernetes e container registry. Non comprende snapshot, regole di rete, backup, audit, metriche o fatturazione. Una famiglia negata o non disponibile è un errore esplicito, non uno zero verificato.

Per VPS o Cloud PRO/Smart delle piattaforme precedenti non presumere visibilità con la nuova CMP. Verifica progetto e ID nel pannello. Inventario CMP vuoto non dimostra che non esistano altre risorse Aruba. Non migrare server o sostituire API precedenti automaticamente.

Per aggiornare controlla https://github.com/Arubacloud/acloud-cli/releases e https://github.com/Arubacloud/sdk-go/releases; verifica checksum e compatibilità, ripeti i test dell'helper e aggiorna la provenienza. Evita aggiornamenti silenziosi durante un'operazione cloud.
