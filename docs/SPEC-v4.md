# SPEC v4.1 — Bot de liquidaciones Morpho Blue, multicadena y "sombra primero"

> Se apoya en `SPEC-v3-morpho-blue-base.md`. **Reutiliza sin cambios** M3 (contrato), M4 (tests) y M5.3–M5.8 (matemática, riesgo, chain, planner), salvo los parches de la sección 5.
> Copia este archivo a `docs/SPEC-v4.md` y úsalo en Cursor con `@docs/SPEC-v4.md` y `@docs/SPEC-v3.md`.
> No soy asesor financiero. **El código del bot no se ha compilado ni ejecutado.** Solo `census_g1.py` se ha probado, con datos sintéticos (no con datos reales).

## Cambios respecto a v4.0

1. **Robinhood Chain pasa de "cadena principal a medir" a cadena de control.** Motivo: tu propio log (≈99% del importe en una dirección). No se descarta del censo; se mide igual y solo pasa a V1 si G1 lo dice.
2. **El censo V0 se amplía** a HyperEVM (999), Katana, World Chain, Monad, Arbitrum (42161) y OP Mainnet (10), además de Base y Robinhood. Flare solo si confirmas que Morpho tiene mercados listados allí.
3. **Los umbrales de G1 no cambian** (top 1 < 60%, bruto fuera del top 1 ≥ 300 $/mes). Propuestas de bajarlos a 150–200 $/mes se rechazan: mover la portería es decidir con los resultados a la vista. Si quieres cambiarlos, hazlo ahora, antes de descargar datos.
4. **Se añade `census_g1.py`** (V-P0 ya implementado). Detalles en la sección 4, V0.
5. **Orden de trabajo:** primero el censo; el esquema SQLite y el bot de sombra solo se construyen si G1 pasa en alguna cadena.

---

## 0. La decisión, con números

**Objetivo declarado:** lucro, con 50–100 € de capital total.

**Lo que dicen los datos medidos hasta hoy**

| Fuente | Resultado |
|---|---|
| Tu M0 en Base (Dune, 22-ago → 28-sep) | Beneficio positivo según Dune: ~470 $ brutos en 5 semanas **si capturaras el 100%**. El resto, polvo o beneficio negativo |
| Censo de terceros, oleada de Base (sep-2026) | 99 liquidaciones, ~19 k$ de incentivo bruto; **un solo liquidador se llevó ~96,8%**, y es un solver de Atlas (subasta OEV) que puja casi todo el excedente. Fuente: github.com/p0nti/arbitrage/pull/12 (análisis de una persona, reproducible con los hashes que cita) |
| Tu log de Robinhood Chain (27-jul → 14-ago, 25 filas) | ~1.940 $ repagados; **0x885d… ≈ 99% del importe** (13 de 25 eventos, un solo mercado); el resto, ~15 $ entre 8 direcciones. Supone deuda de 6 decimales: compruébalo por mercado |
| Panel de Morpho (data.morpho.org/liquidations) | ~38–43 k$ liquidados en 24 h **en todas las cadenas**; 60,8 k$ la semana del 28-sep |
| DefiLlama (30 d, colateral liquidado) | Robinhood ~650 k$, Base ~130 k$, Ethereum ~86 k$, Flare ~62 k$, HyperEVM ~43 k$. **No corroborado** por tu log; no lo uses como dato firme |

**Conclusión honesta:** con lo medido, la esperanza de beneficio de un recién llegado es **cercana a cero** y puede ser negativa. Este spec no promete ingresos: está diseñado para (a) **no perder más de un tope fijado** y (b) **producir una decisión con datos** sobre si hay un hueco real en alguna cadena.

**Regla de oro:** si la puerta G1 (sección 3) falla en todas las cadenas, **se para y no se despliega nada**. Para un objetivo de lucro, parar a tiempo es la mejor decisión disponible.

---

## 1. Todas las opciones consideradas

Etiquetas: **[medido]** datos que tú o yo hemos visto · **[fuente]** dato de terceros · **[sin medir]** no hay datos de competencia.

| # | Opción | Evidencia | Capital | Veredicto |
|---|---|---|---|---|
| 1 | Morpho/Base vía OEV (solver Atlas) | [fuente] ~97% a un solver; los pujadores se comen el excedente | Bonding atlETH + infra | **Descartada** como objetivo |
| 2 | Morpho/Base, mercados pequeños sin OEV | [medido] ~470 $/5 sem. máx.; especialistas por mercado (p. ej. FXRP/RLUSD) | ~0 | **Solo como cadena de control** |
| 3 | Morpho/Robinhood Chain | [medido] 1 dirección ≈ 99% del importe; chain FCFS (carrera de latencia pura); lanzada el 1-jul-2026 | ~0 | **Cadena de control** (G1 probablemente falla; se mide igualmente) |
| 4 | Morpho en cadenas de cola larga (HyperEVM, Katana, World Chain, Monad, Arc, Unichain, Flare…) | [fuente] volúmenes liquidados muy pequeños (panel Morpho, 5-oct: HyperEVM ≈58 M$ en préstamos, −47% en 30 d; Arbitrum ≈6,9 M$, −36%; OP ≈3,1 M$); [fuente] un repo particular describe liquidadores propios en Base, World Chain y Katana, y el bot oficial de Morpho ya tiene venue para HyperEVM; [sin medir] competencia real | ~0 | **Entran en el censo V0**; pasan a V1 solo si G1 las promociona. Hipótesis a contrastar: que G1 falle por importe (pocos $/mes), no por concentración |
| 5 | Morpho/Ethereum | [fuente] mayor flujo en picos (≈238 M$ en una semana de ene-feb 2026, Steakhouse); [sin medir] rivales; gas L1 alto | Gas por intento alto | **Sin dinero** con 100 €. Opcional en sombra como referencia |
| 6 | Pre-liquidaciones de Morpho | [sin medir] adopción | ~0 | **Investigación opcional** en V0 (contar mercados con contrato de pre-liquidación) |
| 7 | Otros protocolos (Aave v3, Moonwell, Euler v2, Fluid, Silo) | [sin medir]; Euler publica bot abierto y usa subasta holandesa | ~0 | **Fuera de alcance de v4**; medirlos con el mismo método V0 si quieres ampliar |
| 8 | Solver de CoW Protocol | [fuente] bond 50–100 k$ + COW, KYC (docs.cow.fi) | Muy alto | **Descartada** |
| 9 | Prestar stablecoins | [fuente] ~3,6–4,3% (Aave/Morpho en Base, 2026) | Todo el capital | ~4 €/año con 100 €. No es bot |
| 10 | Servicios/bounties (auditoría, herramientas, bug bounties) | [sin medir] | 0 | Fuera de este spec |

### Decisión

- **Método:** liquidaciones de Morpho Blue **sin flash loan** (v3), **medidas primero en modo sombra**, con puerta explícita antes de usar dinero.
- **Cadenas:** **no hay cadena principal todavía**: la decide G1. **Base (8453)** y **Robinhood (4663)** son cadenas de control. Candidatas del censo: HyperEVM (999), Katana, World Chain, Monad, Arbitrum (42161), OP (10); Flare solo si Morpho tiene mercados listados allí. Ethereum, solo lectura si quieres comparar.
- **Nota sobre el modelo de beneficio:** en Morpho el neto es incentivo − (precio del oráculo vs. precio del DEX) − gas. Si el oráculo valora el colateral por encima del DEX, la liquidación pierde dinero; no abre ninguna "ventana". Los bots de Morpho no enrutan entre cadenas.
- **Arbitrum/OP como "campo de pruebas" del parche de gas (P1):** eso se prueba en un fork, no hace falta tráfico real.
- **Lenguaje:** **Python** para V0–V3. **Rust solo** si la sombra muestra que pierdes carreras por poco y el neto estimado es positivo (sección 7). Antes sería optimizar a ciegas.
- **Por qué sombra:** el censo dice quién *ganó*, pero no si tú habrías llegado antes. Solo la sombra lo mide, y cuesta ~0.

---

## 2. Presupuesto y topes (fíjalos hoy)

| Concepto | Tope |
|---|---|
| Pérdida total máxima del proyecto | **100 €** (incluye gas de despliegue y de intentos) |
| ETH en la wallet `OPERATOR` (hot wallet) | **≤ 20–30 €** por cadena |
| Infraestructura mensual | Fija un máximo (p. ej. 5–10 €/mes) y compruébalo con los precios actuales de tu proveedor |
| Fallos consecutivos antes de pausar | 3 |
| Gas gastado en intentos fallidos antes de parar | 10 € |

Seguridad: clave del operador solo en variables de entorno, wallet nueva solo para esto, repo privado, gitleaks (como en v3 Fase 2). La clave nunca va en el chat.

---

## 3. Puertas de decisión (con umbrales fijados antes de mirar)

**Las cifras son propuestas: cámbialas ahora, no después de ver resultados.**

### G1 — Censo por cadena (antes de desplegar nada)

Por cada cadena candidata, 90 días, **ponderado por importe repagado** (no por número de eventos: en tu log el top 1 era 52% por eventos y ≈99% por importe).

| Métrica | Umbral para pasar |
|---|---|
| Peso del top 1 en USD repagados | **< 60%** |
| Incentivo bruto acumulado **fuera del top 1** | **≥ 300 $/mes** |
| Mediana de deuda repagada | informativa |
| ¿El top 1 es un contrato de solver/OEV? | si sí, se descarta aunque pase lo demás |

Pasa → V1. No pasa en ninguna → **PARAR** (no hay V1).

### G2 — Sombra (mínimo 21 días por cadena)

Definiciones (para cada liquidación ajena observada en tus mercados):
- **rentable:** tu réplica, con cotización real del swap, habría dado `neto_usd ≥ MIN_PROFIT_USD` en el bloque anterior al del ganador.
- **antes / empate / tarde:** compara tu bloque de primera detección con el bloque del ganador. Los empates **no** cuentan como ganados: en una cadena FCFS el desempate es por orden de llegada y la sombra no lo ve.

| Métrica | Umbral |
|---|---|
| Eventos rentables observados | ≥ 5 (si hay menos: ampliar a 60 días; si sigue habiendo menos: parar) |
| Tasa "antes" sobre rentables | **≥ 40%** |
| Neto estimado acumulado | **≥ 3× el coste de infraestructura** del periodo |

### G3 — Dinero real (solo tras G2)

`MAX_REPAY_USD=300`, `MIN_PROFIT_USD=1`, hot wallet 20–30 €, una cadena cada vez. Para pasar a ampliar: beneficio real > gas + infra durante 14 días y sin incidentes.

**Parar** si: neto real negativo tras 14 días, 3 fallos consecutivos, 10 € de gas en fallos, o cualquier incidente de seguridad.

---

## 4. Fases

### V0 — Censo (1–2 h por cadena)

0. **Cadenas del censo:** Base, Robinhood, HyperEVM (999), Katana, World Chain, Monad, Arbitrum (42161), OP (10). Para cada una, comprueba primero que Morpho tiene mercados listados (panel de Morpho). Los chain IDs de Katana, World Chain y Monad **no están verificados aquí**: confírmalos en docs.morpho.org.
1. Verifica la dirección de Morpho de cada cadena en `docs.morpho.org/developers/contracts/addresses/` y en el explorador (Base: BaseScan; Robinhood: `robinhoodchain.blockscout.com`). **La dirección de Robinhood no está verificada en este documento.**
2. Extrae los eventos `Liquidate` de 90 días: `block_time`, `market_id`, `caller` (liquidador), `borrower`, `repaidAssets`, `seizedAssets`, `badDebtAssets`, `tx_hash`. Nombres exactos del evento en `EventsLib.sol`.
3. Para cada `market_id`: tokens, decimales (**convierte cada importe con los decimales de su token de deuda**), LLTV y LIF (`min(1,15; 1/(0,3·LLTV+0,7))`).
4. Resuelve el `From` real de cada tx; si es un contrato, anota quién lo llamó.
5. Calcula G1. Para volver a usar la API de Morpho: **confirma en el Playground** (`https://api.morpho.org/graphql`) los campos de la consulta de liquidaciones; la documentación actual muestra `marketTransactions` con `where: { chainId_in, userAddress_in }`, `txHash`, `timestamp`, `type`, pero los campos específicos de liquidación (`repaidAssets`, `liquidator`) aparecen en versiones antiguas y deben comprobarse.
6. (Opcional) cuenta cuántos mercados tienen contrato de pre-liquidación.

**Herramienta: `census_g1.py`** (solo librería estándar, sin red). Una invocación por todas las cadenas:

```
python census_g1.py --markets markets.csv \
  --file base=base.csv --file robinhood=robinhood.csv --file hyperevm=hyperevm.csv \
  --file katana=katana.csv --file worldchain=worldchain.csv --file monad=monad.csv \
  --file arbitrum=arbitrum.csv --file op=op.csv \
  --days 90 --top1-max 0.60 --outside-min 300 --solvers 0x... --json censo.json
```

- `markets.csv` es obligatorio (`market_id, loan_decimals, lltv [, loan_usd]`): nunca se asumen decimales. `loan_usd` por defecto es 1,0, válido solo para stablecoins; si el token de deuda no lo es, ponlo. Los `market_id` de cadenas distintas no deberían colisionar (son hashes), así que un único `markets.csv` sirve.
- Los mercados que falten en `markets.csv` se excluyen **y se informan**: revisa esa línea, porque excluir mercados puede cambiar el veredicto.
- `--solvers`: direcciones conocidas de solver/OEV; si el top 1 está ahí, la cadena no pasa.
- Las fechas aceptan `2026-08-14 12:00:00.000 UTC` (Dune), `…T…Z` y `+00:00`.
- Prueba realizada: datos sintéticos de una cadena, comprobados a mano (ponderación por importe, LIF por mercado, exclusión de auto-liquidaciones y de mercados ausentes). **No se ha ejecutado con datos reales.**

**Puerta V0:** tabla por cadena (nº liquidaciones/mes, USD repagados, top 1 y top 3 por importe, bruto fuera del top 1) y veredicto G1.

**Si G1 falla en todas las cadenas: PARAR.** No se escribe V1 ni V2, y tampoco el esquema SQLite.

### V1 — Contrato y tests (solo si G1 pasa)

Usa **M3 y M4 de la v3 sin cambios de lógica**. Cambios:
- `SWAP_ROUTER` es inmutable → **un despliegue por cadena**, con el router de *esa* cadena.
- No asumas que existe un `SwapRouter02` compatible con `exactInput` (Uniswap V3) en cada cadena. En Robinhood Chain hay un AMM tipo Uniswap según varias fuentes, pero versión y direcciones **no están verificadas**. Si el AMM es otra versión, se necesita otro adaptador.
- Los tests de M4 crean su propio mercado con oráculo falso; en cada cadena se ejecutan en fork de esa cadena.
- Oráculos con salvaguardas (p. ej. TWAP) pueden revertir `price()` y bloquear liquidaciones: el planner ya trata `oracle_error`.

**Puerta V1:** `forge build && forge test` en verde por cadena y contrato verificado en el explorador.

### V2 — Bot de sombra multicadena

Se reutilizan `morpho_math.py`, `risk.py`, `chain.py`, `planner.py` de la v3. Novedades:

**Registro de cadenas (`chains.yaml`).** Una entrada por cadena; **solo las que pasen G1, más las de control que quieras**. Los campos marcados `VERIFICAR` no deben rellenarse de memoria. Todas las cadenas, incluidas las de control, arrancan en `mode: shadow`:

```yaml
base:
  chain_id: 8453
  morpho: "0xBBBBBbbBBb9cC5e90e3b3Af64bdAF62C37EEFFCb"   # VERIFICAR otra vez en docs oficiales
  rpc_http: ${BASE_RPC_HTTP}
  rpc_ws: ${BASE_RPC_WS}
  swap_router: VERIFICAR
  quoter: VERIFICAR
  weth: "0x4200000000000000000000000000000000000006"
  gas_model: op_stack            # coste L1 vía GasPriceOracle (como v3)
  enabled: true
  mode: shadow
robinhood:                       # cadena de control: nunca pasa a mode: live salvo que G1 y G2 lo justifiquen
  chain_id: 4663
  morpho: VERIFICAR
  rpc_http: ${ROBINHOOD_RPC_HTTP}   # público: rpc.mainnet.chain.robinhood.com (comprobar límites)
  rpc_ws: ${ROBINHOOD_RPC_WS}
  swap_router: VERIFICAR
  quoter: VERIFICAR
  weth: VERIFICAR
  gas_model: arbitrum_nitro      # VERIFICAR: ver parche P1
  enabled: true
  mode: shadow
```

**Un proceso por cadena** (aislamiento de fallos), mismo código, distinta configuración.

**Detección.** Igual que v3 (escaneo por bloque con Multicall3). En Robinhood los bloques son de ~100 ms según las fuentes: **mide** cuántas llamadas por segundo aguanta tu RPC antes de nada (`probe_rpc.py` de la v2). Si no sigues el ritmo de bloques, tu "detección" siempre llegará tarde y el resultado de la sombra será un artefacto de tu infraestructura, no del mercado.

**Modo sombra = no hay transacciones.** Prueba obligatoria: con `MODE=shadow`, ninguna ruta de código llama a `send_raw_transaction`.

**Qué se registra (SQLite, por cadena):**

```sql
CREATE TABLE flagged (            -- posiciones que tu réplica marca como no saludables
  chain TEXT, market_id TEXT, borrower TEXT,
  first_flag_block INTEGER, first_flag_ts_local REAL,
  ltv REAL, lltv REAL, oracle_price TEXT,
  PRIMARY KEY (chain, market_id, borrower, first_flag_block)
);
CREATE TABLE plan (               -- lo que habrías hecho
  chain TEXT, market_id TEXT, borrower TEXT, block INTEGER,
  repaid_assets TEXT, seized TEXT, dex_quote TEXT, gas_cost_loan TEXT,
  net_usd REAL, decision TEXT, reason TEXT
);
CREATE TABLE observed (           -- verdad: liquidaciones ajenas
  chain TEXT, tx_hash TEXT PRIMARY KEY, block INTEGER, block_ts INTEGER,
  market_id TEXT, borrower TEXT, caller TEXT, tx_from TEXT,
  repaid_assets TEXT, seized_assets TEXT, bad_debt TEXT
);
CREATE TABLE verdict (            -- cruce observed ↔ flagged/plan
  chain TEXT, tx_hash TEXT, profitable INTEGER,
  our_first_flag_block INTEGER, winner_block INTEGER,
  bucket TEXT CHECK (bucket IN ('antes','empate','tarde','no_detectado')),
  net_usd_est REAL
);
```

**Informe semanal automático** (Telegram o CSV): por cadena, eventos rentables, % antes/empate/tarde/no detectado, neto estimado, y **top 1/top 3 por importe**.

**Puerta V2:** 1 hora sin excepciones en cada cadena, con latidos, y al menos una liquidación ajena cruzada correctamente en `verdict`.

### V3 — Sombra (≥ 21 días por cadena)

Corre V2 y evalúa G2. Revisa semanalmente que tu **retraso de detección** (hora local de recepción del bloque frente al instante de inclusión) sea coherente con la cadena; si el 100% de los casos sale "tarde", comprueba primero tu RPC antes de concluir nada.

### V4 — Dinero real (solo si G2 pasa)

Sigue M6–M8 de la v3, con los topes de la sección 2. Una cadena a la vez, `MODE=live`, `MAX_REPAY_USD=300`.

---

## 5. Parches sobre la v3 (necesarios para multicadena)

**P1 — Coste de gas L1 por tipo de cadena.** La v3 usa `getL1Fee` (OP-stack/Base). Robinhood Chain es Arbitrum Orbit (Nitro): ahí el componente L1 no se obtiene con ese oráculo. **Verifica** en la documentación de Arbitrum el método correcto (el precompile `NodeInterface` con `gasEstimateComponents`) antes de implementarlo. Hasta entonces, usa `estimate_gas` ×1,3 como cota conservadora y marca el coste como "estimado".

**P2 — Orden de transacciones.** En Base, la prioridad se compra con propina; en Robinhood (FCFS) la propina **no** adelanta, solo cuenta el instante de llegada al sequencer. El planner no debe gastar propina en FCFS; `executor.py` lee `ordering: priority_fee | fcfs` de `chains.yaml`.

**P3 — Rutas de swap por cadena.** `routes.json` pasa a `routes.<cadena>.json`. Los colaterales de Robinhood son en gran parte acciones tokenizadas; **la liquidez en DEX y su horario de mercado no están verificados**: la ruta debe cotizarse con `Quoter` real y descartarse si no hay.

**P4 — Variables por cadena.** Prefija las variables (`BASE_*`, `ROBINHOOD_*`) y añade `MODE` (`shadow|live`), `ORDERING` y `GAS_MODEL`.

---

## 6. Cursor: reglas y prompts

### Reglas (`.cursor/rules/project.mdc`, añade a las de la v3)

```
- Modo por defecto: MODE=shadow. Ninguna ruta de código debe poder enviar transacciones en shadow.
- Todo dato específico de una cadena (direcciones, router, quoter, gas_model, ordering) sale de chains.yaml. Prohibido hardcodear direcciones en código.
- Los campos marcados VERIFICAR no se rellenan de memoria: pregunta o deja un TODO.
- Convertir importes con los decimales de cada token (nunca asumir 6 ni 18).
- Las métricas de competencia se ponderan por importe, no por número de eventos.
- Antes de dar algo por terminado: ejecutar la "Puerta" de esa fase y pegar la salida.
```

### Prompts

**V-P0 — Censo.** "Lee @docs/SPEC-v4.md sección V0. Dame un script Python que, a partir de un CSV exportado (Dune/Blockscout) con las columnas de la sección V0, calcule por cadena: eventos/mes, USD repagados (con decimales por token), top 1 y top 3 por importe, y el bruto fuera del top 1 usando el LIF de cada mercado. Que imprima el veredicto G1. No consultes ninguna API."

**V-P1 — Registro de cadenas.** "Crea `chains.py` y `chains.yaml` según V2. Falla al arrancar si queda algún campo `VERIFICAR`. Test: la carga rechaza una cadena incompleta."

**V-P2 — Sombra.** "Implementa el esquema SQLite de V2 y el cruce `observed ↔ flagged` que rellena `verdict` con los cuatro buckets. Añade el test que prueba que con MODE=shadow no se llama nunca a `send_raw_transaction`."

**V-P3 — Informe.** "Genera el informe semanal de V2 (por cadena: rentables, % antes/empate/tarde/no_detectado, neto estimado, top 1/top 3 por importe) y los tests con datos sintéticos."

**V-P4 — Gas por cadena.** "Implementa P1 y P2: `gas_model` y `ordering` en el executor. Para `arbitrum_nitro`, deja un TODO con el enlace a la documentación hasta que yo confirme el método."

**V-P5 — Auditoría.** "Revisa el repo: rutas donde MODE=live pueda activarse por accidente, direcciones hardcodeadas, importes sin decimales, `except` que oculten errores, desviaciones de SPEC-v4. Lista priorizada con rutas y líneas."

---

## 7. Cuándo portar a Rust

Solo si, tras G2, se cumplen **ambas**: (a) los casos "tarde" se pierden por 1–2 bloques o menos, y tu retraso medido está dominado por tu código y no por tu RPC; (b) el neto estimado de esos casos, si se hubieran ganado, supera el coste de infraestructura. En una cadena FCFS, el lenguaje pesa menos que la distancia de red al sequencer, la conexión persistente, las transacciones pre-firmadas y el estado en memoria; medirlo antes evita invertir en lo equivocado.

---

## 8. Estado de verificación

**Añadido en v4.1 (de terceros, sin contrastar de forma independiente):** cifras de préstamos del panel de Morpho del 5-oct (HyperEVM, Arbitrum, OP); existencia de un venue de HyperEVM en el bot oficial de Morpho; repositorio de un particular con liquidadores en Base, World Chain y Katana. **NO verificado:** chain IDs de Katana, World Chain y Monad; que Morpho tenga mercados listados en Flare.

**Contrastado en esta conversación:** chain ID 4663 de Robinhood Chain, FCFS, bloques ~100 ms y lanzamiento el 1-jul-2026 (varios documentos de infraestructura); cifras de liquidaciones del panel de Morpho y de DefiLlama; análisis de Base de github.com/p0nti/arbitrage/pull/12; requisitos de bonding/KYC de CoW (docs.cow.fi); rangos de rendimiento de stablecoins; datos de tu log de Robinhood (cálculos propios, decimales supuestos).

**NO verificado:** dirección de Morpho en Robinhood Chain; routers, quoters, versión de Uniswap y liquidez de los colaterales en Robinhood; método de coste L1 en Nitro (P1); campos de liquidación de la API de Morpho; que los datos de DefiLlama sean representativos; cualquier dato de competencia en cadenas de cola larga y en otros protocolos; todo el código del bot (nada se ha compilado ni ejecutado). `census_g1.py` solo se ha probado con datos sintéticos.

**Fuera de alcance:** asesoramiento financiero, legal o fiscal.
