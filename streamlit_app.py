import streamlit as st
import pandas as pd
import requests
from io import StringIO
from datetime import datetime
import plotly.express as px
import math
import unicodedata

# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────
def safe_int(x, default=0):
    try:
        if x is None:
            return default
        if isinstance(x, float) and math.isnan(x):
            return default
        if isinstance(x, str) and x.strip().lower() in {"", "nan", "none", "null", "n/a"}:
            return default
        return int(float(str(x).replace(",", ".")))
    except Exception:
        return default

def parse_int_list(value):
    if value is None:
        return []
    if isinstance(value, float) and math.isnan(value):
        return []
    parts = [p.strip() for p in str(value).split(",")]
    out = []
    for p in parts:
        if not p:
            continue
        v = safe_int(p, None)
        if v is not None:
            out.append(v)
    return out

def normaliza_codigo(s):
    return str(s).strip().upper()

# ─────────────────────────────────────────────────────────────
# Config página
# ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Estoque Cockpit - Silva Holding",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URLs (ajuste se trocar)
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxTX9uUWnByw6sk6MtuJ5FbjV7zeBKYEoUPPlUlUDS738QqocfCd_NAlh9Eh25XhQywTw/exec"

# ─────────────────────────────────────────────────────────────
# Carregar produtos (com deduplicação por codigo_norm)
# ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def carregar_produtos():
    try:
        r = requests.get(SHEETS_URL, timeout=15)
        r.raise_for_status()
        df = pd.read_csv(StringIO(r.text))

        # Garante colunas
        base_cols = ['codigo','nome','categoria','estoque_atual','estoque_min','estoque_max','eh_kit','componentes','quantidades']
        for c in base_cols:
            if c not in df.columns:
                df[c] = "" if c in ['nome','categoria','eh_kit','componentes','quantidades'] else 0

        # Tipos numéricos
        for c in ['estoque_atual','estoque_min','estoque_max']:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        # Normaliza/Cria chave e remove duplicados
        df['codigo_norm'] = df['codigo'].apply(normaliza_codigo)
        # Em caso de duplicados, manter a ÚLTIMA ocorrência (troque para 'first' se preferir)
        df = df.sort_values(by=['codigo_norm']).drop_duplicates(subset=['codigo_norm'], keep='last').reset_index(drop=True)

        # Blindagem texto
        for c in ['nome','categoria','eh_kit','componentes','quantidades']:
            df[c] = df[c].astype(str).fillna('')

        # Derivados
        df['estoque_max'] = pd.to_numeric(df['estoque_max'], errors='coerce').fillna(0)
        df.loc[df['estoque_max'].eq(0), 'estoque_max'] = (df['estoque_min'] * 2).astype(int)

        return df
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {e}")
        return pd.DataFrame()

# ─────────────────────────────────────────────────────────────
# Semáforo
# ─────────────────────────────────────────────────────────────
def calcular_semaforo(a, mn, mx):
    if a < mn:
        return "CRÍTICO", "#ff4444"
    elif a <= mn * 1.2:
        return "BAIXO", "#ffaa00"
    elif a > mx:
        return "EXCESSO", "#0088ff"
    else:
        return "OK", "#00aa00"

# ─────────────────────────────────────────────────────────────
# Chamar webhook (ou simular)
# ─────────────────────────────────────────────────────────────
def movimentar_estoque(codigo, quantidade, tipo, colaborador, simulation, estoque_atual=None):
    if simulation:
        novo = (estoque_atual or 0) + (quantidade if tipo == 'entrada' else -quantidade)
        return {'success': True, 'message': 'Simulado', 'novo_estoque': int(novo)}
    try:
        payload = {'codigo': codigo, 'quantidade': int(quantidade), 'tipo': tipo, 'colaborador': colaborador}
        resp = requests.post(WEBHOOK_URL, json=payload, timeout=20)
        return resp.json()
    except Exception as e:
        return {'success': False, 'message': f'Erro: {e}'}

# ─────────────────────────────────────────────────────────────
# Expandir kits em componentes
# ─────────────────────────────────────────────────────────────
def expandir_kits(df_fatura, produtos_df):
    kits_dict = {}
    for _, row in produtos_df.iterrows():
        if str(row.get('eh_kit','')).strip().lower() == 'sim':
            cod = row['codigo_norm']
            comps = [normaliza_codigo(c) for c in str(row.get('componentes','')).split(',') if c and c.strip()]
            quants = parse_int_list(row.get('quantidades',''))
            if comps and quants and len(comps)==len(quants):
                kits_dict[cod] = list(zip(comps, quants))

    if not kits_dict:
        return df_fatura

    linhas = []
    for _, r in df_fatura.iterrows():
        cod = r['codigo_norm']
        q = safe_int(r.get('quantidade',0),0)
        if cod in kits_dict:
            for c,qc in kits_dict[cod]:
                linhas.append({'codigo_norm': c, 'quantidade': q*safe_int(qc,0)})
        else:
            linhas.append({'codigo_norm': cod, 'quantidade': q})

    out = pd.DataFrame(linhas)
    return out.groupby('codigo_norm', as_index=False)['quantidade'].sum()

# ─────────────────────────────────────────────────────────────
# Processar faturamento (robusto e sem índice duplicado)
# ─────────────────────────────────────────────────────────────
def processar_faturamento(arquivo_upload, produtos_df):
    try:
        nome = arquivo_upload.name.lower()
        if nome.endswith('.csv'):
            df = None
            for enc in ['utf-8','utf-8-sig','latin1','iso-8859-1','cp1252','windows-1252']:
                try:
                    arquivo_upload.seek(0)
                    df = pd.read_csv(arquivo_upload, encoding=enc)
                    if df is not None and len(df.columns)>0:
                        break
                except:
                    continue
            if df is None:
                return None, None, "Não foi possível ler o CSV. Tente UTF-8."
        elif nome.endswith('.xlsx'):
            df = pd.read_excel(arquivo_upload, engine='openpyxl')
        elif nome.endswith('.xls'):
            df = pd.read_excel(arquivo_upload, engine='xlrd')
        else:
            return None, None, "Formato não suportado. Use CSV/XLS/XLSX."

        # normaliza colunas
        def norm_col(c):
            c = unicodedata.normalize('NFKD', str(c)).encode('ASCII','ignore').decode('ASCII')
            return c.lower().strip()
        df.rename(columns={c: norm_col(c) for c in df.columns}, inplace=True)

        if 'codigo' not in df.columns or 'quantidade' not in df.columns:
            return None, None, f"Arquivo deve ter colunas 'codigo' e 'quantidade'. Encontradas: {list(df.columns)}"

        df['codigo_norm'] = df['codigo'].apply(normaliza_codigo)
        df['quantidade']   = df['quantidade'].apply(lambda x: safe_int(x,0)).astype(int)
        df = df[(df['codigo_norm']!='') & (df['quantidade']>0)]
        df = df.groupby('codigo_norm', as_index=False)['quantidade'].sum()

        # expande kits
        df = expandir_kits(df, produtos_df)

        # quem existe no estoque?
        cods_estoque = set(produtos_df['codigo_norm'])
        df['encontrado'] = df['codigo_norm'].isin(cods_estoque)

        encontrados = df[df['encontrado']].copy().reset_index(drop=True)
        nao_encontrados = df[~df['encontrado']].copy().reset_index(drop=True)

        if not encontrados.empty:
            base = produtos_df[['codigo_norm','nome','estoque_atual']].copy()
            base = base.dropna(subset=['codigo_norm'])
            base = base.drop_duplicates(subset=['codigo_norm'], keep='last')
            # NÃO usa orient='index' com índices duplicados :)
            est_map = base.set_index('codigo_norm')[['nome','estoque_atual']].to_dict(orient='index')

            encontrados['nome'] = encontrados['codigo_norm'].map(lambda x: est_map.get(x, {}).get('nome', 'N/A'))
            encontrados['estoque_atual'] = encontrados['codigo_norm'].map(lambda x: est_map.get(x, {}).get('estoque_atual', 0))
            encontrados['estoque_atual'] = pd.to_numeric(encontrados['estoque_atual'], errors='coerce').fillna(0).astype(int)
            encontrados['quantidade'] = pd.to_numeric(encontrados['quantidade'], errors='coerce').fillna(0).astype(int)
            encontrados['estoque_final'] = encontrados['estoque_atual'] - encontrados['quantidade']

        return encontrados, nao_encontrados, None
    except Exception as e:
        return None, None, f"Erro ao processar: {e}"

# ─────────────────────────────────────────────────────────────
# Estilos
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
.cockpit {background: linear-gradient(90deg,#1e3c72,#2a5298); color:#fff; padding:14px; border-radius:10px; margin-bottom:12px;}
.metric {background:linear-gradient(135deg,#667eea,#764ba2); color:#fff; padding:10px; border-radius:10px; text-align:center;}
.warn {background:#fff3cd; border-left:4px solid #ffc107; padding:10px; border-radius:6px;}
.ok {background:#d4edda; border-left:4px solid #28a745; padding:10px; border-radius:6px;}
.err {background:#f8d7da; border-left:4px solid #dc3545; padding:10px; border-radius:6px;}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Header
# ─────────────────────────────────────────────────────────────
st.markdown('<div class="cockpit"><h2>COCKPIT DE CONTROLE — SILVA HOLDING</h2><p>"Se parar para sentir o perfume das rosas, vem um caminhão e te atropela."</p></div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# Base
# ─────────────────────────────────────────────────────────────
produtos_df = carregar_produtos()
if produtos_df.empty:
    st.stop()

# semáforos
status_list = []
cor_list = []
for _, r in produtos_df.iterrows():
    stt, cor = calcular_semaforo(r['estoque_atual'], r['estoque_min'], r['estoque_max'])
    status_list.append(stt); cor_list.append(cor)
produtos_df['status'] = status_list
produtos_df['cor'] = cor_list

# ─────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────
st.sidebar.header("🧭 CONTROLES DE VOO")
simulation_mode = st.sidebar.checkbox("✍️ Modo Teste (simulação, não altera planilha)", value=True)
st.sidebar.markdown(
    "Todas as operações serão **simuladas** quando o Modo Teste estiver ativo. "
    "Nada será enviado ao Google Apps Script."
)

categorias = ['Todas'] + sorted(produtos_df['categoria'].dropna().unique().tolist())
cat = st.sidebar.selectbox("Categoria", categorias)
sts = st.sidebar.selectbox("Status", ['Todos','CRÍTICO','BAIXO','OK','EXCESSO'])
aba = st.sidebar.radio("Tipo de Análise", ["Visão Geral","Análise Mín/Máx","Movimentação","Baixa por Faturamento","Histórico de Baixas","Relatório de Faltantes"])

df_view = produtos_df.copy()
if cat!='Todas': df_view = df_view[df_view['categoria']==cat]
if sts!='Todos': df_view = df_view[df_view['status']==sts]

# ─────────────────────────────────────────────────────────────
# Visão Geral
# ─────────────────────────────────────────────────────────────
if aba=="Visão Geral":
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1: st.markdown(f'<div class="metric"><h4>Produtos</h4><h2>{len(df_view)}</h2></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="metric"><h4>Estoque Total</h4><h2>{int(df_view["estoque_atual"].sum()):,}</h2></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="metric"><h4>Críticos</h4><h2>{(df_view["status"]=="CRÍTICO").sum()}</h2></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="metric"><h4>Baixos</h4><h2>{(df_view["status"]=="BAIXO").sum()}</h2></div>', unsafe_allow_html=True)
    with c5: st.markdown(f'<div class="metric"><h4>OK</h4><h2>{(df_view["status"]=="OK").sum()}</h2></div>', unsafe_allow_html=True)

    left,right = st.columns(2)
    with left:
        st.subheader("Distribuição por Status")
        cnt = df_view['status'].value_counts()
        if len(cnt)>0:
            fig = px.pie(values=cnt.values, names=cnt.index,
                         color=cnt.index,
                         color_discrete_map={'CRÍTICO':'#ff4444','BAIXO':'#ffaa00','OK':'#00aa00','EXCESSO':'#0088ff'})
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para o filtro atual.")
    with right:
        st.subheader("Estoque por Categoria")
        g = df_view.groupby('categoria')['estoque_atual'].sum().sort_values(ascending=False)
        st.bar_chart(g)

    st.subheader("🚨 Produtos críticos e baixos")
    crit = df_view[df_view['status'].isin(['CRÍTICO','BAIXO'])].sort_values('estoque_atual')
    if crit.empty:
        st.success("Nenhum produto crítico/baixo nos filtros atuais.")
    else:
        st.dataframe(crit[['codigo','nome','estoque_atual','estoque_min','estoque_max','status']], use_container_width=True, height=420)

# ─────────────────────────────────────────────────────────────
# Análise Mín / Máx
# ─────────────────────────────────────────────────────────────
elif aba=="Análise Mín/Máx":
    st.subheader("Análise de Estoque Mín/Máx")
    opt = st.selectbox("Métrica", ["Falta para Mínimo","Falta para Máximo","Excesso sobre Máximo","Diferença Mín-Máx"])
    df = df_view.copy()
    df['falta_min'] = (df['estoque_min'] - df['estoque_atual']).clip(lower=0)
    df['falta_max'] = (df['estoque_max'] - df['estoque_atual']).clip(lower=0)
    df['excesso_max'] = (df['estoque_atual'] - df['estoque_max']).clip(lower=0)
    df['dif_mm'] = df['estoque_max'] - df['estoque_min']
    col_map = {
        "Falta para Mínimo": "falta_min",
        "Falta para Máximo": "falta_max",
        "Excesso sobre Máximo": "excesso_max",
        "Diferença Mín-Máx": "dif_mm"
    }
    col = col_map[opt]
    df = df[df[col]>0].sort_values(col, ascending=False)
    if df.empty:
        st.info("Nada a exibir para este filtro.")
    else:
        st.dataframe(df[['codigo','nome','estoque_atual','estoque_min','estoque_max',col,'status']], use_container_width=True, height=460)

# ─────────────────────────────────────────────────────────────
# Movimentação manual
# ─────────────────────────────────────────────────────────────
elif aba=="Movimentação":
    st.subheader("Movimentação de Estoque")
    colaborador = st.selectbox("Colaborador", ['Pericles','Maria','Camila','Cris VantiStella'])
    busca = st.text_input("Buscar por código ou nome", "")
    if len(busca)>=2:
        res = df_view[df_view['codigo'].str.contains(busca,case=False,na=False) | df_view['nome'].str.contains(busca,case=False,na=False)]
        if res.empty:
            st.warning("Nenhum produto encontrado.")
        else:
            for _, p in res.head(5).iterrows():
                with st.expander(f"{p['codigo']} — {p['nome']} (Estoque: {int(p['estoque_atual'])})"):
                    c1,c2 = st.columns(2)
                    with c1:
                        qtd = st.number_input("Entrada (quantidade)", min_value=1, value=1, key=f"ent_{p['codigo']}")
                        if st.button("+ Entrada", key=f"btn_ent_{p['codigo']}"):
                            r = movimentar_estoque(p['codigo'], qtd, 'entrada', colaborador, simulation_mode, estoque_atual=int(p['estoque_atual']))
                            st.success(f"{r.get('message','OK')} • Novo estoque: {r.get('novo_estoque','N/A')}")
                    with c2:
                        qs = st.number_input("Saída (quantidade)", min_value=1, value=1, key=f"sai_{p['codigo']}")
                        if st.button("- Saída", key=f"btn_sai_{p['codigo']}"):
                            r = movimentar_estoque(p['codigo'], qs, 'saida', colaborador, simulation_mode, estoque_atual=int(p['estoque_atual']))
                            st.success(f"{r.get('message','OK')} • Novo estoque: {r.get('novo_estoque','N/A')}")
    else:
        st.info("Digite ao menos 2 caracteres para buscar.")

# ─────────────────────────────────────────────────────────────
# Baixa por Faturamento (com SIMULAÇÃO)
# ─────────────────────────────────────────────────────────────
elif aba=="Baixa por Faturamento":
    st.subheader("Baixa por Faturamento")
    st.markdown(f"""<div class="ok"><b>Modo Teste:</b> <code>{'ATIVO (simulação)' if simulation_mode else 'DESLIGADO (altera planilha)'}</code></div>""", unsafe_allow_html=True)
    colaborador = st.selectbox("Colaborador responsável", ['Pericles','Maria','Camila','Cris VantiStella'], key="colab_fat")

    up = st.file_uploader("Arquivo de faturamento (CSV, XLS, XLSX) — requer colunas 'codigo' e 'quantidade'", type=['csv','xls','xlsx'])
    if up:
        with st.spinner("Processando..."):
            encontrados, nao, erro = processar_faturamento(up, produtos_df)
        if erro:
            st.error(erro)
        else:
            c1,c2,c3 = st.columns(3)
            with c1: st.metric("Linhas totais", (0 if encontrados is None else len(encontrados)) + (0 if nao is None else len(nao)))
            with c2: st.metric("Encontrados", 0 if encontrados is None else len(encontrados))
            with c3: st.metric("Não encontrados", 0 if nao is None else len(nao))

            if nao is not None and not nao.empty:
                st.markdown("#### ❌ Produtos não encontrados (não serão baixados)")
                st.dataframe(nao[['codigo_norm','quantidade']].rename(columns={'codigo_norm':'Código','quantidade':'Quantidade'}), use_container_width=True, height=200)
                st.download_button("📥 Baixar faltantes (CSV)", nao[['codigo_norm','quantidade']].rename(columns={'codigo_norm':'codigo'}).to_csv(index=False).encode('utf-8-sig'), "codigos_faltantes.csv", "text/csv")

            if encontrados is not None and not encontrados.empty:
                st.markdown("---")
                st.markdown("### Preview da Baixa")
                prev = encontrados[['codigo_norm','nome','estoque_atual','quantidade','estoque_final']].copy()
                prev.columns = ['Código','Produto','Estoque Atual','Qtd a Baixar','Estoque Final']
                prev['Status'] = prev['Estoque Final'].apply(lambda x: 'Negativo' if x<0 else ('Zerado' if x==0 else 'OK'))
                st.dataframe(prev, use_container_width=True, height=420)

                total = int(prev['Qtd a Baixar'].sum())
                negs = int((prev['Estoque Final']<0).sum())
                zers = int((prev['Estoque Final']==0).sum())
                d1,d2,d3 = st.columns(3)
                with d1: st.metric("Total a baixar", f"{total:,}")
                with d2: st.metric("Ficam negativos", negs)
                with d3: st.metric("Ficam zerados", zers)

                st.markdown("---")
                if st.button(("🔁 SIMULAR BAIXAS" if simulation_mode else "✅ APLICAR BAIXAS")):
                    resultados = []
                    okc, errc = 0, 0
                    prog = st.progress(0)
                    for i, row in encontrados.iterrows():
                        r = movimentar_estoque(
                            codigo=row['codigo_norm'],
                            quantidade=int(row['quantidade']),
                            tipo='saida',
                            colaborador=colaborador,
                            simulation=simulation_mode,
                            estoque_atual=int(row['estoque_atual'])
                        )
                        if r.get('success'):
                            okc += 1
                            resultados.append({
                                'codigo': row['codigo_norm'],
                                'nome': row['nome'],
                                'qtd_baixada': int(row['quantidade']),
                                'estoque_anterior': int(row['estoque_atual']),
                                'estoque_final': r.get('novo_estoque','N/A'),
                                'status': '✅ Sucesso (simulado)' if simulation_mode else '✅ Sucesso',
                                'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'colaborador': colaborador
                            })
                        else:
                            errc += 1
                            resultados.append({
                                'codigo': row['codigo_norm'],
                                'nome': row['nome'],
                                'qtd_baixada': int(row['quantidade']),
                                'estoque_anterior': int(row['estoque_atual']),
                                'estoque_final': 'N/A',
                                'status': f"❌ Erro: {r.get('message','desconhecido')}",
                                'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'colaborador': colaborador
                            })
                        prog.progress((i+1)/len(encontrados))
                    prog.empty()

                    st.success(f"Processo concluído • Sucessos: {okc} • Erros: {errc}")
                    rel = pd.DataFrame(resultados)
                    st.dataframe(rel[['codigo','nome','qtd_baixada','estoque_anterior','estoque_final','status']], use_container_width=True, height=420)
                    st.download_button("📥 Baixar relatório (CSV)", rel.to_csv(index=False).encode('utf-8-sig'),
                                       f"relatorio_baixas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")
                    st.cache_data.clear()

# ─────────────────────────────────────────────────────────────
# Histórico (placeholder para quando a aba existir na planilha)
# ─────────────────────────────────────────────────────────────
elif aba=="Histórico de Baixas":
    st.info("Aba de histórico pode ser ligada à guia 'historico_baixas' da sua planilha. (módulo pronto para plugar)")

# ─────────────────────────────────────────────────────────────
# Relatório de Faltantes
# ─────────────────────────────────────────────────────────────
elif aba=="Relatório de Faltantes":
    st.subheader("Relatório de Faltantes")
    up = st.file_uploader("Arquivo de vendas (CSV/XLS/XLSX)", type=['csv','xls','xlsx'])
    if up:
        try:
            nome = up.name.lower()
            if nome.endswith('.csv'):
                df = pd.read_csv(up, encoding='latin1')
            elif nome.endswith('.xlsx'):
                df = pd.read_excel(up, engine='openpyxl')
            else:
                df = pd.read_excel(up, engine='xlrd')

            df.columns = [c.lower().strip() for c in df.columns]
            if 'codigo' not in df.columns or 'quantidade' not in df.columns:
                st.error(f"Colunas necessárias: 'codigo' e 'quantidade'. Encontradas: {list(df.columns)}")
            else:
                df['codigo_norm'] = df['codigo'].apply(normaliza_codigo)
                df['quantidade'] = df['quantidade'].apply(lambda x: safe_int(x,0)).astype(int)
                df = df.groupby('codigo_norm', as_index=False)['quantidade'].sum()

                faltas = []
                base = produtos_df.set_index('codigo_norm')
                for _, r in df.iterrows():
                    cod = r['codigo_norm']; q = int(r['quantidade'])
                    if cod in base.index:
                        prod = base.loc[cod]
                        if str(prod.get('eh_kit','')).strip().lower() == 'sim':
                            comps = [normaliza_codigo(c) for c in str(prod.get('componentes','')).split(',') if c and c.strip()]
                            quants = parse_int_list(prod.get('quantidades',''))
                            for c, qk in zip(comps, quants):
                                neces = q*safe_int(qk,0)
                                if c in base.index:
                                    est = int(base.loc[c].get('estoque_atual',0))
                                    if est < neces:
                                        faltas.append([cod, c, base.loc[c].get('nome',''), est, neces, neces-est, 'Componente de Kit'])
                                else:
                                    faltas.append([cod, c, 'NÃO CADASTRADO', 0, neces, neces, 'Componente NÃO Cadastrado'])
                        else:
                            est = int(prod.get('estoque_atual',0))
                            if est < q:
                                faltas.append(['-', cod, prod.get('nome',''), est, q, q-est, 'Produto Normal'])
                    else:
                        faltas.append(['-', cod, 'NÃO CADASTRADO', 0, q, q, 'Produto NÃO Cadastrado'])

                if not faltas:
                    st.success("Todos os itens possuem estoque suficiente.")
                else:
                    out = pd.DataFrame(faltas, columns=['Kit Original','Código','Produto','Estoque Atual','Qtd Necessária','Falta','Tipo'])
                    st.dataframe(out, use_container_width=True, height=420)
                    st.download_button("📥 Baixar faltantes (CSV)", out.to_csv(index=False).encode('utf-8-sig'),
                                       f"faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv", "text/csv")

# ─────────────────────────────────────────────────────────────
# Rodapé
# ─────────────────────────────────────────────────────────────
st.markdown("---")
b1,b2,b3 = st.columns(3)
with b1:
    if st.button("Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()
with b2:
    st.write(f"**Última atualização:** {datetime.now().strftime('%H:%M:%S')}")
with b3:
    st.write(f"**Filtros:** {cat} | {sts} | {'Simulação ON' if simulation_mode else 'Simulação OFF'}")
