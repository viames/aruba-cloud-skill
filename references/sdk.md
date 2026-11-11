# Integrazione diretta con sdk-go

Fonti: https://github.com/Arubacloud/sdk-go e https://arubacloud.github.io/sdk-go/

Il checkout esaminato l'11 novembre 2026 era `5865434930b3e74c5cd2e2023d42948a79156d3b`; go.mod richiede Go 1.24.0 con toolchain 1.24.10. La CLI inclusa usa sdk-go v1.0.4. Non trasferire esempi da main a versioni precedenti senza verificarne le firme. Per nuovi progetti scegli una release verificata e fissala in go.mod; conserva go.sum. Evita `@latest` durante operazioni di produzione.

Client raccomandato con valori da ambiente del processo o secret manager:

```go
client, err := aruba.NewClient(aruba.DefaultOptions(clientID, clientSecret))
if err != nil { return err }
ctx, cancel := context.WithTimeout(context.Background(), 2*time.Minute)
defer cancel()
projects, err := client.FromProject().List(ctx, aruba.WithLimit(50))
if err != nil { return err }
err = projects.All(ctx, func(p *aruba.Project) bool {
    // Consuma ID e metadati nel chiamante; non loggare secret o token.
    return true
})
```

Import: `github.com/Arubacloud/sdk-go/pkg/aruba`, oltre a context e time. Le reference accettano wrapper ottenuti dal client o `aruba.URI("/projects/" + projectID)` per un progetto noto.

Domini: `FromProject`, `FromCompute`, `FromNetwork`, `FromStorage`, `FromDatabase`, `FromContainer`, `FromSecurity`, `FromSchedule`, `FromMetric`, `FromAudit`. Verifica la disponibilità nella versione scelta. Filtri e paging: `WithFilter`, `WithSort`, `WithLimit`, `WithOffset`.

Gli errori HTTP sono ispezionabili con `errors.As` verso `*aruba.HTTPError`. Evita log dell'errore completo se contiene corpi, header o dettagli sensibili; registra stato HTTP e un riferimento locale dell'operazione.

Creare un progetto è sincrono; molte altre risorse sono asincrone. `WaitUntilReady` accetta anche Stopped: per accensione/spegnimento usa uno stato finale esplicito e controlla le firme nella versione installata. `PowerOn` e `PowerOff` richiedono un CloudServer ottenuto dal client con Get/List. Gli esempi all-resources creano risorse e possono generare costi: non usarli come test della connessione.
