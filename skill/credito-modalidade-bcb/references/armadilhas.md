# Armadilhas da fonte, em detalhe

## Formato original e cobertura

A API do SGS entrega uma resposta por código de série, com apenas `data` (DD/MM/AAAA, sempre
dia 01) e `valor` (texto decimal). Não existe consulta multi-série: o painel faz uma
requisição por código (61 no total) e anota `segmento`, `modalidade` e `medida` a partir de
um mapa próprio. As 61 séries cobrem os mesmos meses (mar/2011 em diante), sem lacunas,
então comparar modalidades não tem viés de janela.

| Item | Valor |
|---|---|
| Granularidade | mensal, nacional |
| Segmentos | Total (PF + PJ), PF, PJ |
| Combinações | 29 (3 agregados, 10 modalidades PF, 16 PJ) |
| Medidas | saldo (R$ milhões), taxa (% a.a.), spread (p.p. a.a.) |
| Início | mar/2011 (o saldo existe desde 2007, o total desde 1988, mas juros e spread só a partir de 2011) |
| Licença | Open Database License (ODbL) — Banco Central do Brasil |

## Unidades

- `saldo`: **R$ milhões**. 1.400.000 significa R$ 1,4 trilhão. Converta para uma unidade
  legível ao escrever ("R$ 7,4 trilhões") e diga a unidade.
- `taxa_juros_aa`: **% ao ano**, já em percentual (39,44 é 39,44%, não 0,3944).
- `spread_pp`: **pontos percentuais ao ano**. É a taxa média de juros menos o custo médio de
  captação. Variações de taxa e de spread se dizem em p.p.

## Spread só nos agregados

O BCB publica spread apenas para Total, PF e PJ. 26 das 29 combinações têm `spread_pp`
nulo em todos os meses. É ausência com significado: preencher com zero, interpolar ou tirar
média ignorando nulos produz números inventados.

## Estoque e fluxo na mesma linha

`saldo` é a posição da carteira no último dia do mês (estoque). `taxa_juros_aa` é a taxa
média das operações contratadas naquele mês (fluxo). Somar saldos de meses consecutivos não
tem significado, e a taxa de um mês descreve o preço do dinheiro novo, não o custo da
carteira existente.

## Taxas não se somam: ponderar pelo saldo

Em jun/2026 as taxas PF iam de 10,64% a.a. (crédito rural) a 442,44% a.a. (cartão
rotativo), amplitude de 41 vezes. A maior carteira PF é a mais barata: financiamento
imobiliário, cerca de R$ 1,4 trilhão a 11,22%. A média simples das dez modalidades PF dá
algo perto de 100% a.a.; a ponderada pelo saldo, que é o que o segmento de fato paga, foi
39,44%. Toda agregação de taxa deve ser ponderada pelo saldo.

## Cobertura parcial e o resíduo "Outras modalidades"

As modalidades detalhadas não esgotam o segmento: somam cerca de 82% do saldo PF e 70% do
PJ. O restante é o resíduo `saldo do Total do segmento − soma das modalidades`, que o painel
exibe como "Outras modalidades". Ao calcular participação, o denominador é o `Total` do
segmento, e a diferença até 100% é esse resíduo. Ele não é uma série da fonte: é calculado.

## Valores nominais

Sem correção pela inflação. O saldo cresceu mais de 4 vezes em 15 anos em termos nominais;
parte disso é inflação. Para comparar anos distantes, deflacione pelo IPCA (SGS 433) com
`--ipca` e mostre nominal e real. Taxa e spread são percentuais e não precisam de deflação
(mas a taxa é nominal, não real: não a compare com a inflação sem descontá-la).

## Nacional, e não por UF

O SGS não publica crédito por UF por modalidade. Existe crédito por estado apenas por porte
de empresa (microempresa, pequeno porte, MEI), um recorte diferente que não se cruza com
este. Já verificado: esta fonte é nacional.

## Revisões e atraso

O BCB divulga o mês de referência cerca de quatro semanas depois e pode revisar meses já
publicados. Diferenças pequenas entre o seu resultado e outra fonte podem vir daí.
Informe sempre o último mês disponível usado.

## Outras ressalvas

- A taxa média das concessões pode ser ponderada pelo volume dentro de cada modalidade ou
  ser média simples das instituições; a metodologia não está clara na página do SGS. Evite
  conclusões finas sobre diferenças de poucas décimas.
- Crédito rural e BNDES têm taxas administradas ou subsidiadas: taxa baixa não indica
  baixo risco.
- Cartão de crédito aparece em duas linhas (rotativo e parcelado). Elas não equivalem ao
  total de cartão, que inclui a compra à vista, sem juros.
