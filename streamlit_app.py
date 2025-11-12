import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import plotly.express as px
from io import StringIO
import math
import unicodedata

# ======================
# Helpers robustos
# ======================
def safe_int(x, default=0):
    """Converte qualquer coisa para int sem quebrar (lida com 'nan', NaN, '', '3,0', etc.)."""
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
    """'1,2, 3' -> [1,2,3]; ignora nulos/NaN/vazios."""
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

# ======================
# Config da página
# ======================
st.set_page_config(
    page_title="Estoque Cockpit - Silva Holding",
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ======================
# URLs externas
# ======================
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"

# Deployment atual do Apps Script (produção)
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxTX9uUWnByw6sk6MtuJ5FbjV7zeBKYEoUPPlUlUDS738QqocfCd_NAlh9Eh25XhQywTw/exec"

# ======================
# Carregar produtos
# ======================
@st.cache_data(ttl=30)
def carregar_produtos():
    try:
        response = requests.get(SHEETS_URL, timeout=10)
        response.raise_for_status()
        csv_data = StringIO(response.text)
        df = pd.read_csv(csv_data)

        # Colunas essenciais
        required = ['codigo','nome','categoria','estoque_atual','estoque_min','estoque_max']
        for c in required:
            if c not in df.columns:
                df[c] = 0

        # Numéricos
        for c in ['estoque_atual','estoque_min','estoque_max']:
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0)

        # Colunas de kit
        for c in ['componentes','quantidades','eh_kit']:
            if c not in df.columns:
                df[c] = ''
            else:
                df[c] = df[c].astype(str).fillna('')

        # Normaliza códigos
        df['codigo_norm'] = df['codigo'].astype(str).str.strip().str.upper()
        return df
    except Exception as e:
        st.error(f"Erro ao carregar dados: {e}")
        return pd.DataFrame()

# ======================
# Semáforo
# ======================
def calcular_semaforo(estoque_atual, estoque_min, estoque_max):
    if estoque_atual < estoque_min:
        return "", "CRÍTICO", "#ff4444"
    elif estoque_atual <= estoque_min * 1.2:
        return "", "BAIXO", "#ffaa00"
    elif estoque_atual > estoque_max:
        return "", "EXCESSO", "#0088ff"
    else:
        return "", "OK", "#00aa00"

# ======================
# POST real (produção)
# ======================
def movimentar_estoque_real(codigo, quantidade, tipo, colaborador):
    try:
        payload = {
            'codigo': str(codigo).strip(),
            'quantidade': safe_int(quantidade, 0),
            'tipo': tipo,
            'colaborador': colaborador
        }
        r = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        try:
            return r.json()
        except Exception:
            return {'success': False, 'message': f'Resposta inesperada do servidor: {r.text[:200]}'}
    except Exception as e:
        return {'success': False, 'message': f'Erro: {e}'}

# ======================
# SIMULAÇÃO (não altera planilha)
# ======================
def movimentar_estoque_simulado(codigo, quantidade, tipo, colaborador, estoque_local):
    """
    Atualiza um dicionário local de estoque e retorna resultado simulado.
    Não chama webhook e não altera planilha.
    """
    cod = str(codigo).strip().upper()
    qtd = safe_int(quantidade, 0)
    atual = safe_int(estoque_local.get(cod, 0), 0)
    if tipo == 'entrada':
        novo = atual + qtd
    else:  # 'saida'
        novo = atual - qtd  # permite negativo na simulação (para testar alerta)
    estoque_local[cod] = novo
    return {
        'success': True,
        'message': 'Operação simulada (nenhuma alteração na planilha).',
        'novo_estoque': novo,
        'simulado': True
    }

# ======================
# Expandir kits
# ======================
def expandir_kits(df_fatura, produtos_df):
    kits = {}
    for _, row in produtos_df.iterrows():
        if str(row.get('eh_kit','')).strip().lower() == 'sim':
            cod = str(row.get('codigo','')).strip().upper()
            if not cod:
                continue
            comps = [c.strip().upper() for c in str(row.get('componentes','')).split(',') if c and c.strip()]
            qts = parse_int_list(row.get('quantidades',''))
            if comps and qts and len(comps)==len(qts):
                kits[cod] = list(zip(comps, qts))

    if not kits:
        return df_fatura

    linhas = []
    for _, r in df_fatura.iterrows():
        cod = str(r['codigo']).strip().upper()
        qtd = safe_int(r.get('quantidade',0), 0)
        if cod in kits:
            for comp, comp_q in kits[cod]:
                linhas.append({'codigo': comp, 'quantidade': qtd * safe_int(comp_q,0)})
        else:
            linhas.append({'codigo': cod, 'quantidade': qtd})

    out = pd.DataFrame(linhas).groupby('codigo', as_index=False)['quantidade'].sum()
    return out

# ======================
# Processar faturamento (leitura + matching)
# ======================
def processar_faturamento(arquivo_upload, produtos_df):
    try:
        nome = arquivo_upload.name.lower()

        if nome.endswith('.csv'):
            df = None
            for enc in ['utf-8','utf-8-sig','latin1','iso-8859-1','cp1252','windows-1252']:
                try:
                    arquivo_upload.seek(0)
                    tmp = pd.read_csv(arquivo_upload, encoding=enc)
                    if tmp is not None and tmp.shape[1] > 0:
                        df = tmp
                        break
                except:
                    continue
            if df is None:
                return None, None, "Não foi possível ler o CSV. Salve como UTF-8."
        elif nome.endswith('.xlsx'):
            df = pd.read_excel(arquivo_upload, engine='openpyxl')
        elif nome.endswith('.xls'):
            df = pd.read_excel(arquivo_upload, engine='xlrd')
        else:
            return None, None, "Formato não suportado. Use CSV, XLS ou XLSX."

        # Normaliza colunas
        def norm_col(c):
            c = unicodedata.normalize('NFKD', str(c)).encode('ASCII','ignore').decode('ASCII')
            return c.lower().strip()
        df.rename(columns={c: norm_col(c) for c in df.columns}, inplace=True)

        if 'codigo' not in df.columns:
            return None, None, f"Arquivo sem coluna 'Código'. Colunas: {list(df.columns)}"
        if 'quantidade' not in df.columns:
            return None, None, f"Arquivo sem coluna 'Quantidade'. Colunas: {list(df.columns)}"

        # Limpeza
        df['codigo'] = df['codigo'].astype(str).str.strip()
        df['quantidade'] = df['quantidade'].apply(lambda x: safe_int(x, 0)).astype(int)
        df = df[(df['codigo']!='') & (df['quantidade']>0)]
        df = df.groupby('codigo', as_index=False)['quantidade'].sum()

        # Expande kits
        df = expandir_kits(df, produtos_df)

        # Match
        codset = set(produtos_df['codigo_norm'])
        df['codigo_norm'] = df['codigo'].str.upper()
        df['encontrado'] = df['codigo_norm'].isin(codset)

        encontrados = df[df['encontrado']].copy().reset_index(drop=True)
        nao = df[~df['encontrado']].copy().reset_index(drop=True)

        if not encontrados.empty:
            est_map = produtos_df.set_index('codigo_norm')[['nome','estoque_atual']].to_dict(orient='index')
            encontrados['nome'] = encontrados['codigo_norm'].map(lambda c: est_map.get(c,{}).get('nome','N/A'))
            encontrados['estoque_atual'] = encontrados['codigo_norm'].map(lambda c: est_map.get(c,{}).get('estoque_atual',0))
            encontrados['estoque_atual'] = pd.to_numeric(encontrados['estoque_atual'], errors='coerce').fillna(0)
            encontrados['quantidade'] = pd.to_numeric(encontrados['quantidade'], errors='coerce').fillna(0)
            encontrados['estoque_final'] = encontrados['estoque_atual'] - encontrados['quantidade']

        return encontrados, nao, None
    except Exception as e:
        return None, None, f"Erro ao processar faturamento: {e}"

# ======================
# CSS
# ======================
st.markdown("""
<style>
.metric-card{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);padding:1rem;border-radius:10px;color:#fff;text-align:center;margin:.5rem 0}
.status-card{padding:1rem;border-radius:8px;margin:.3rem 0;border-left:4px solid}
.critico{border-color:#ff4444;background:#ffe6e6}
.baixo{border-color:#ffaa00;background:#fff8e6}
.ok{border-color:#00aa00;background:#e6ffe6}
.excesso{border-color:#0088ff;background:#e6f3ff}
.cockpit-header{background:linear-gradient(90deg,#1e3c72 0%,#2a5298 100%);color:#fff;padding:1rem;border-radius:10px;text-align:center;margin-bottom:1rem}
.warning-box{background:#fff3cd;border-left:4px solid #ffc107;padding:1rem;border-radius:5px;margin:1rem 0}
.success-box{background:#d4edda;border-left:4px solid #28a745;padding:1rem;border-radius:5px;margin:1rem 0}
.error-box{background:#f8d7da;border-left:4px solid #dc3545;padding:1rem;border-radius:5px;margin:1rem 0}
.test-banner{background:#e8f0fe;border-left:6px solid #1a73e8;padding:.75rem 1rem;border-radius:8px;margin:.5rem 0}
</style>
""", unsafe_allow_html=True)

# ======================
# Header
# ======================
st.markdown("""
<div class="cockpit-header">
    <h1>COCKPIT DE CONTROLE - SILVA HOLDING</h1>
    <p>"Se parar para sentir o perfume das rosas, vem um caminhão e te atropela"</p>
</div>
""", unsafe_allow_html=True)

# ======================
# Dados base
# ======================
produtos_df = carregar_produtos()
if produtos_df.empty:
    st.error("Não foi possível carregar os dados da planilha.")
    st.stop()

# Semáforos e derivados
produtos_df['semaforo'], produtos_df['status'], produtos_df['cor'] = zip(*produtos_df.apply(
    lambda r: calcular_semaforo(r['estoque_atual'], r['estoque_min'], r['estoque_max']), axis=1
))
produtos_df['falta_para_min'] = (produtos_df['estoque_min'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['falta_para_max'] = (produtos_df['estoque_max'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['excesso_sobre_max'] = (produtos_df['estoque_atual'] - produtos_df['estoque_max']).clip(lower=0)
produtos_df['diferenca_min_max'] = produtos_df['estoque_max'] - produtos_df['estoque_min']

# ======================
# Sidebar (inclui Modo Teste)
# ======================
st.sidebar.header("🎛️ CONTROLES DE VOO")
SIMULACAO = st.sidebar.checkbox("🧪 Modo Teste (simulação, não altera planilha)", value=True)
if SIMULACAO:
    st.sidebar.markdown(
        '<div class="test-banner">Todas as operações serão <b>simuladas</b>. Nada será enviado ao Google Apps Script nem alterará a planilha.</div>',
        unsafe_allow_html=True
    )

categorias = ['Todas'] + sorted(produtos_df['categoria'].astype(str).unique().tolist())
categoria_filtro = st.sidebar.selectbox("📂 Categoria:", categorias)
status_opcoes = ['Todos', 'CRÍTICO', 'BAIXO', 'OK', 'EXCESSO']
status_filtro = st.sidebar.selectbox("🚦 Status:", status_opcoes)

tipo_analise = st.sidebar.radio(
    "Tipo de Análise:",
    ["Visão Geral", "Análise Mín/Máx", "Movimentação", "Baixa por Faturamento", "Histórico de Baixas", "Relatório de Faltantes"]
)

# Filtros
df_filtrado = produtos_df.copy()
if categoria_filtro != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['categoria'] == categoria_filtro]
if status_filtro != 'Todos':
    df_filtrado = df_filtrado[df_filtrado['status'] == status_filtro]

# Estoque LOCAL para simulação (dict cod_norm -> estoque)
estoque_local = {row['codigo_norm']: safe_int(row['estoque_atual'],0) for _,row in produtos_df.iterrows()}

# ======================
# Visão Geral
# ======================
if tipo_analise == "Visão Geral":
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1:
        st.markdown(f'<div class="metric-card"><h3>PRODUTOS</h3><h2>{len(df_filtrado)}</h2></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><h3>ESTOQUE TOTAL</h3><h2>{int(df_filtrado["estoque_atual"].sum()):,}</h2></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><h3>CRÍTICOS</h3><h2>{(df_filtrado["status"]=="CRÍTICO").sum()}</h2></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><h3>BAIXOS</h3><h2>{(df_filtrado["status"]=="BAIXO").sum()}</h2></div>', unsafe_allow_html=True)
    with c5:
        st.markdown(f'<div class="metric-card"><h3>OK</h3><h2>{(df_filtrado["status"]=="OK").sum()}</h2></div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Distribuição por Status")
        cnt = df_filtrado['status'].value_counts()
        fig = px.pie(values=cnt.values, names=cnt.index, color=cnt.index,
                     color_discrete_map={'CRÍTICO':'#ff4444','BAIXO':'#ffaa00','OK':'#00aa00','EXCESSO':'#0088ff'})
        fig.update_layout(height=300)
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        st.subheader("📈 Estoque por Categoria")
        g = df_filtrado.groupby('categoria')['estoque_atual'].sum().sort_values(ascending=False)
        st.bar_chart(g)

    st.subheader("🚨 PRODUTOS EM SITUAÇÃO CRÍTICA")
    crit = df_filtrado[df_filtrado['status'].isin(['CRÍTICO','BAIXO'])].sort_values('estoque_atual')
    if crit.empty:
        st.success("Nenhum produto em situação crítica!")
    else:
        for _, p in crit.head(10).iterrows():
            klass = p['status'].lower()
            st.markdown(
                f'<div class="status-card {klass}"><strong>{p["semaforo"]} {p["codigo"]}</strong> - {p["nome"]}<br>'
                f'<small>Atual: {int(p["estoque_atual"])} | Mínimo: {int(p["estoque_min"]) } | Falta: {int(p["falta_para_min"])}</small></div>',
                unsafe_allow_html=True
            )

# ======================
# Análise Mín/Máx
# ======================
elif tipo_analise == "Análise Mín/Máx":
    st.subheader("ANÁLISE ESTOQUE MÍNIMO/MÁXIMO")
    c1, c2 = st.columns(2)
    with c1:
        analise_tipo = st.selectbox("Tipo de Análise:", ["Falta para Mínimo","Falta para Máximo","Excesso sobre Máximo","Diferença Mín-Máx"])
    with c2:
        only_diff = st.checkbox("Mostrar apenas com diferença > 0", value=True)

    df_a = df_filtrado.copy()
    if analise_tipo=="Falta para Mínimo":
        col = 'falta_para_min'; titulo='Falta p/ Mín'
        if only_diff: df_a = df_a[df_a[col] > 0]
    elif analise_tipo=="Falta para Máximo":
        col = 'falta_para_max'; titulo='Falta p/ Máx'
        if only_diff: df_a = df_a[df_a[col] > 0]
    elif analise_tipo=="Excesso sobre Máximo":
        col = 'excesso_sobre_max'; titulo='Excesso s/ Máx'
        if only_diff: df_a = df_a[df_a[col] > 0]
    else:
        col = 'diferenca_min_max'; titulo='Diferença Mín-Máx'
        if only_diff: df_a = df_a[df_a[col] > 0]

    if df_a.empty:
        st.info("ℹ️ Nenhum produto com os critérios selecionados.")
    else:
        tbl = df_a[['codigo','nome','categoria','estoque_atual','estoque_min','estoque_max',col,'status']].copy()
        tbl.columns = ['Código','Produto','Categoria','Atual','Mínimo','Máximo',titulo,'Status']
        for c in ['Atual','Mínimo','Máximo',titulo]:
            tbl[c] = pd.to_numeric(tbl[c], errors='coerce').fillna(0).astype(int)
        st.dataframe(tbl.sort_values(titulo, ascending=False), use_container_width=True, height=420)

        st.subheader(f"Top 20 — {analise_tipo}")
        top = df_a.nlargest(20, col)
        st.bar_chart(top.set_index('codigo')[col])

# ======================
# Movimentação (manual) — com simulação
# ======================
elif tipo_analise == "Movimentação":
    st.subheader("MOVIMENTAÇÃO DE ESTOQUE")
    if SIMULACAO:
        st.markdown('<div class="test-banner">🔬 <b>Modo Teste:</b> entradas/saídas abaixo são apenas simulação.</div>', unsafe_allow_html=True)

    colaboradores = ['Pericles','Maria','Camila','Cris VantiStella']
    colaborador = st.selectbox("👤 Colaborador:", colaboradores)
    busca = st.text_input("🔍 Buscar produto:", placeholder="Digite código ou nome...")

    if not busca:
        st.info("Digite ao menos 2 caracteres para buscar.")
    else:
        if len(busca) < 2:
            st.warning("Use 2+ caracteres para refinar a busca.")
        else:
            found = df_filtrado[
                df_filtrado['codigo'].astype(str).str.contains(busca, case=False, na=False) |
                df_filtrado['nome'].astype(str).str.contains(busca, case=False, na=False)
            ]
            if found.empty:
                st.warning("Nenhum produto encontrado.")
            else:
                for _, produto in found.head(5).iterrows():
                    with st.expander(f"{produto['codigo']} - {produto['nome']}"):
                        c1, c2, c3 = st.columns(3)
                        with c1:
                            st.metric("Estoque Atual", f"{int(produto['estoque_atual'])}")
                            st.metric("Mínimo", f"{int(produto['estoque_min'])}")
                            st.metric("Máximo", f"{int(produto['estoque_max'])}")

                        with c2:
                            st.write("**ENTRADA**")
                            qtd_e = st.number_input("Quantidade (entrada):", min_value=1, value=1, key=f"ent_{produto['codigo']}")
                            if st.button("+ Entrada", key=f"btn_ent_{produto['codigo']}"):
                                if SIMULACAO:
                                    res = movimentar_estoque_simulado(produto['codigo'], qtd_e, 'entrada', colaborador, estoque_local)
                                else:
                                    res = movimentar_estoque_real(produto['codigo'], qtd_e, 'entrada', colaborador)
                                if res.get('success'):
                                    st.success(f"Entrada {'SIMULADA' if SIMULACAO else 'realizada'}! Novo estoque: {res.get('novo_estoque')}")
                                else:
                                    st.error(res.get('message','Erro desconhecido'))

                        with c3:
                            st.write("**SAÍDA**")
                            max_s = max(1, int(produto['estoque_atual']))
                            qtd_s = st.number_input("Quantidade (saída):", min_value=1, value=1, key=f"sai_{produto['codigo']}")
                            if st.button("- Saída", key=f"btn_sai_{produto['codigo']}"):
                                if SIMULACAO:
                                    res = movimentar_estoque_simulado(produto['codigo'], qtd_s, 'saida', colaborador, estoque_local)
                                else:
                                    res = movimentar_estoque_real(produto['codigo'], qtd_s, 'saida', colaborador)
                                if res.get('success'):
                                    st.success(f"Saída {'SIMULADA' if SIMULACAO else 'realizada'}! Novo estoque: {res.get('novo_estoque')}")
                                else:
                                    st.error(res.get('message','Erro desconhecido'))

# ======================
# Baixa por Faturamento — com simulação
# ======================
elif tipo_analise == "Baixa por Faturamento":
    st.subheader("BAIXA POR FATURAMENTO")

    st.markdown("""
    <div class="success-box">
        <strong>Fluxo:</strong><br>
        1) Upload do arquivo (CSV/XLS/XLSX com 'Código' e 'Quantidade')<br>
        2) Preview: encontrados x não encontrados + estoques finais<br>
        3) Botão de <b>simular</b> ou <b>aplicar</b> baixas
    </div>
    """, unsafe_allow_html=True)

    if SIMULACAO:
        st.markdown('<div class="test-banner">🔬 <b>Modo Teste ativo:</b> ao processar, será <b>SIMULAÇÃO</b>. A planilha não será alterada.</div>', unsafe_allow_html=True)

    colaboradores = ['Pericles','Maria','Camila','Cris VantiStella']
    colaborador_fatura = st.selectbox("👤 Colaborador responsável:", colaboradores, key="colab_fatura")

    up = st.file_uploader("📁 Arquivo de faturamento", type=['csv','xls','xlsx'], help="Deve conter colunas 'Código' e 'Quantidade'.")

    if up is not None:
        with st.spinner("Processando arquivo..."):
            encontrados, nao, erro = processar_faturamento(up, produtos_df)

        if erro:
            st.error(erro)
        else:
            c1,c2,c3 = st.columns(3)
            with c1:
                total_linhas = len(encontrados) + len(nao)
                st.metric("Total de Linhas", total_linhas)
            with c2:
                st.metric("Produtos Encontrados", len(encontrados))
            with c3:
                st.metric("Produtos NÃO Encontrados", len(nao))

            if not nao.empty:
                st.markdown("---")
                st.markdown('<div class="error-box"><b>ATENÇÃO:</b> Os códigos abaixo não existem no cadastro e não serão baixados.</div>', unsafe_allow_html=True)
                nao_tbl = nao[['codigo','quantidade']].copy()
                nao_tbl.columns = ['Código','Quantidade Solicitada']
                st.dataframe(nao_tbl, use_container_width=True, height=200)
                st.download_button(
                    "📥 Baixar Códigos Faltantes (CSV)",
                    nao_tbl.to_csv(index=False, encoding='utf-8-sig'),
                    file_name=f"codigos_faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

            if not encontrados.empty:
                st.markdown("---")
                st.subheader("Preview da Baixa")

                preview = encontrados[['codigo','nome','estoque_atual','quantidade','estoque_final']].copy()
                preview.columns = ['Código','Produto','Estoque Atual','Qtd a Baixar','Estoque Final']
                for c in ['Estoque Atual','Qtd a Baixar','Estoque Final']:
                    preview[c] = pd.to_numeric(preview[c], errors='coerce').fillna(0).astype(int)
                preview['Status'] = preview['Estoque Final'].apply(lambda x: 'Negativo' if x<0 else ('Zerado' if x==0 else 'OK'))
                st.dataframe(preview, use_container_width=True, height=420)

                c1,c2,c3 = st.columns(3)
                with c1:
                    st.metric("Total a Baixar", f"{int(preview['Qtd a Baixar'].sum()):,}")
                with c2:
                    st.metric("Ficarão Negativos", int((preview['Estoque Final']<0).sum()))
                with c3:
                    st.metric("Ficarão Zerados", int((preview['Estoque Final']==0).sum()))

                st.markdown("---")
                if SIMULACAO:
                    # Só SIMULAR
                    if st.button("🧪 SIMULAR BAIXAS (sem alterar planilha)", type="primary", use_container_width=True):
                        resultados = []
                        # aplica em estoque_local
                        for _, r in encontrados.iterrows():
                            cod = r['codigo_norm']
                            qtd = safe_int(r['quantidade'],0)
                            antes = safe_int(estoque_local.get(cod,0),0)
                            # aplica saída simulada
                            res = movimentar_estoque_simulado(r['codigo'], qtd, 'saida', colaborador_fatura, estoque_local)
                            resultados.append({
                                'codigo': r['codigo'],
                                'nome': r['nome'],
                                'qtd_baixada': qtd,
                                'estoque_anterior': antes,
                                'estoque_final': res.get('novo_estoque', 'N/A'),
                                'status': '🧪 Simulado',
                                'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                'colaborador': colaborador_fatura
                            })
                        st.success("Simulação concluída. Nenhuma alteração realizada na planilha.")
                        df_res = pd.DataFrame(resultados)
                        show = df_res[['codigo','nome','qtd_baixada','estoque_anterior','estoque_final','status']]
                        show.columns = ['Código','Produto','Qtd Baixada','Estoque Anterior','Estoque Final','Status']
                        st.dataframe(show, use_container_width=True, height=420)
                        st.download_button(
                            "📥 Baixar Relatório da Simulação (CSV)",
                            df_res.to_csv(index=False, encoding='utf-8-sig'),
                            file_name=f"simulacao_baixas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                else:
                    # Aplicar de verdade
                    if st.button("✅ CONFIRMAR E APLICAR BAIXAS (altera planilha)", type="primary", use_container_width=True):
                        sucessos, erros, resultados = 0, 0, []
                        progress = st.progress(0)
                        status_txt = st.empty()
                        total = len(encontrados)

                        for i, r in encontrados.iterrows():
                            status_txt.text(f"Processando {i+1}/{total}: {r['codigo']}")
                            resp = movimentar_estoque_real(r['codigo'], r['quantidade'], 'saida', colaborador_fatura)
                            if resp.get('success'):
                                sucessos += 1
                                resultados.append({
                                    'codigo': r['codigo'],
                                    'nome': r['nome'],
                                    'qtd_baixada': r['quantidade'],
                                    'estoque_anterior': r['estoque_atual'],
                                    'estoque_final': resp.get('novo_estoque','N/A'),
                                    'status': '✅ Sucesso',
                                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'colaborador': colaborador_fatura
                                })
                            else:
                                erros += 1
                                resultados.append({
                                    'codigo': r['codigo'],
                                    'nome': r['nome'],
                                    'qtd_baixada': r['quantidade'],
                                    'estoque_anterior': r['estoque_atual'],
                                    'estoque_final': 'N/A',
                                    'status': f"❌ Erro: {resp.get('message','Desconhecido')}",
                                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'colaborador': colaborador_fatura
                                })
                            progress.progress((i+1)/total)

                        progress.empty(); status_txt.empty()
                        st.subheader("📄 Relatório de Baixas Realizadas")
                        c1,c2,c3 = st.columns(3)
                        with c1: st.metric("✅ Sucessos", sucessos)
                        with c2: st.metric("❌ Erros", erros)
                        with c3: st.metric("📊 Total", sucessos+erros)

                        df_res = pd.DataFrame(resultados)
                        show = df_res[['codigo','nome','qtd_baixada','estoque_anterior','estoque_final','status']]
                        show.columns = ['Código','Produto','Qtd Baixada','Estoque Anterior','Estoque Final','Status']
                        st.dataframe(show, use_container_width=True, height=420)
                        st.download_button(
                            "📥 Baixar Relatório Completo (CSV)",
                            df_res.to_csv(index=False, encoding='utf-8-sig'),
                            file_name=f"relatorio_baixas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv"
                        )
                        st.cache_data.clear()

# ======================
# Histórico de Baixas (somente leitura)
# ======================
elif tipo_analise == "Histórico de Baixas":
    st.title("📊 HISTÓRICO DE BAIXAS POR FATURAMENTO")
    st.markdown("""
    <div class="warning-box">
        Este histórico é lido da aba <b>historico_baixas</b> no Google Sheets (produção).
        Simulações não escrevem nessa aba.
    </div>
    """, unsafe_allow_html=True)
    try:
        HIST_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/gviz/tq?tqx=out:csv&sheet=historico_baixas"
        r = requests.get(HIST_URL, timeout=10)
        r.raise_for_status()
        dfh = pd.read_csv(StringIO(r.text))
        if dfh.empty:
            st.info("📄 Nenhuma baixa registrada ainda.")
        else:
            if 'qtd_baixada' in dfh.columns:
                dfh['qtd_baixada'] = pd.to_numeric(dfh['qtd_baixada'], errors='coerce').fillna(0)

            c1,c2,c3,c4 = st.columns(4)
            with c1: st.metric("📊 Total Linhas", len(dfh))
            with c2: st.metric("📦 Total Unidades", int(dfh.get('qtd_baixada',pd.Series()).sum()) if 'qtd_baixada' in dfh else "N/A")
            with c3: st.metric("👥 Colaboradores", dfh.get('colaborador', pd.Series()).nunique() if 'colaborador' in dfh else "N/A")
            with c4:
                if 'status' in dfh.columns:
                    ok = len(dfh[dfh['status'].astype(str).str.contains('Sucesso', na=False)])
                    st.metric("✅ Taxa Sucesso", f"{ok/len(dfh)*100:.1f}%")
                else:
                    st.metric("✅ Taxa Sucesso", "N/A")

            # Filtros
            c1,c2,c3 = st.columns(3)
            with c1:
                if 'colaborador' in dfh.columns:
                    sel_colab = st.selectbox("👤 Colaborador:", ['Todos'] + sorted(dfh['colaborador'].astype(str).unique().tolist()))
                else:
                    sel_colab = 'Todos'
            with c2:
                sel_status = st.selectbox("🚦 Status:", ['Todos','Sucesso','Erro'] if 'status' in dfh.columns else ['Todos'])
            with c3:
                sel_periodo = st.selectbox("📅 Período:", ['Todos','Últimas 24h','Últimos 7 dias','Últimos 30 dias'] if 'data_hora' in dfh.columns else ['Todos'])

            dfv = dfh.copy()
            if sel_colab!='Todos' and 'colaborador' in dfv.columns:
                dfv = dfv[dfv['colaborador']==sel_colab]
            if sel_status!='Todos' and 'status' in dfv.columns:
                if sel_status=='Sucesso':
                    dfv = dfv[dfv['status'].astype(str).str.contains('Sucesso', na=False)]
                else:
                    dfv = dfv[dfv['status'].astype(str).str.contains('Erro', na=False)]
            if sel_periodo!='Todos' and 'data_hora' in dfv.columns:
                dfv['data_hora'] = pd.to_datetime(dfv['data_hora'], errors='coerce')
                now = datetime.now()
                if sel_periodo=='Últimas 24h':
                    dfv = dfv[dfv['data_hora'] >= now - pd.Timedelta(days=1)]
                elif sel_periodo=='Últimos 7 dias':
                    dfv = dfv[dfv['data_hora'] >= now - pd.Timedelta(days=7)]
                elif sel_periodo=='Últimos 30 dias':
                    dfv = dfv[dfv['data_hora'] >= now - pd.Timedelta(days=30)]

            st.dataframe(dfv, use_container_width=True, height=520)
            st.download_button(
                "📥 Baixar Histórico Filtrado (CSV)",
                dfv.to_csv(index=False, encoding='utf-8-sig'),
                file_name=f"historico_baixas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    except requests.exceptions.HTTPError:
        st.warning("""
        ⚠️ Aba de histórico não encontrada.
        Crie a aba **historico_baixas** com colunas:
        codigo, nome, qtd_baixada, estoque_anterior, estoque_final, status, data_hora, colaborador
        """)
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

# ======================
# Relatório de Faltantes
# ======================
elif tipo_analise == "Relatório de Faltantes":
    st.title("RELATÓRIO DE PRODUTOS FALTANTES")
    st.markdown("""
    <div class="warning-box">
        Faça upload do arquivo de vendas (código, quantidade). O sistema expande kits e aponta faltas.
        <b>Não altera a planilha</b> — é só diagnóstico/planejamento.
    </div>
    """, unsafe_allow_html=True)

    up = st.file_uploader("Arquivo de vendas (CSV/XLS/XLSX)", type=['csv','xls','xlsx'])
    if up:
        try:
            nome = up.name.lower()
            if nome.endswith('.csv'):
                df_v = pd.read_csv(up, encoding='latin1')
            elif nome.endswith('.xlsx'):
                df_v = pd.read_excel(up, engine='openpyxl')
            elif nome.endswith('.xls'):
                df_v = pd.read_excel(up, engine='xlrd')
            else:
                st.error("Formato não suportado."); st.stop()

            df_v = df_v.reset_index(drop=True)
            df_v.columns = df_v.columns.str.lower().str.strip()
            if 'codigo' not in df_v.columns or 'quantidade' not in df_v.columns:
                st.error(f"Colunas necessárias ausentes. Encontradas: {list(df_v.columns)}"); st.stop()

            df_v['codigo'] = df_v['codigo'].astype(str).str.strip()
            df_v['quantidade'] = df_v['quantidade'].apply(lambda x: safe_int(x,0)).astype(int)
            df_v = df_v.groupby('codigo', as_index=False)['quantidade'].sum()

            # Expande kits e valida faltas
            faltas = []
            map_prod = produtos_df.set_index('codigo_norm').to_dict(orient='index')

            for _, row in df_v.iterrows():
                cod = row['codigo']; qtd = safe_int(row['quantidade'],0)
                cod_norm = cod.upper()
                prod_line = produtos_df[produtos_df['codigo_norm']==cod_norm]
                if prod_line.empty:
                    faltas.append({'kit_original':'-','codigo_componente':cod,'nome':'NÃO CADASTRADO',
                                   'estoque_atual':0,'qtd_necessaria':int(qtd),'falta':int(qtd),'tipo':'Produto NÃO Cadastrado'})
                else:
                    p = prod_line.iloc[0]
                    if str(p.get('eh_kit','')).strip().lower()=='sim':
                        comps = [c.strip().upper() for c in str(p.get('componentes','')).split(',') if c and c.strip()]
                        qts = parse_int_list(p.get('quantidades',''))
                        for comp, qk in zip(comps, qts):
                            q_nec = safe_int(qtd,0)*safe_int(qk,0)
                            comp_line = produtos_df[produtos_df['codigo_norm']==comp.upper()]
                            if comp_line.empty:
                                faltas.append({'kit_original':cod,'codigo_componente':comp,'nome':'NÃO CADASTRADO',
                                               'estoque_atual':0,'qtd_necessaria':int(q_nec),'falta':int(q_nec),'tipo':'Componente NÃO Cadastrado'})
                            else:
                                comp_row = comp_line.iloc[0]
                                est = safe_int(comp_row.get('estoque_atual',0),0)
                                if est < q_nec:
                                    faltas.append({'kit_original':cod,'codigo_componente':comp,'nome':comp_row.get('nome',''),
                                                   'estoque_atual':est,'qtd_necessaria':int(q_nec),'falta':int(q_nec - est),'tipo':'Componente de Kit'})
                    else:
                        est = safe_int(p.get('estoque_atual',0),0)
                        if est < qtd:
                            faltas.append({'kit_original':'-','codigo_componente':cod,'nome':p.get('nome',''),
                                           'estoque_atual':est,'qtd_necessaria':int(qtd),'falta':int(qtd - est),'tipo':'Produto Normal'})

            st.markdown("---")
            if faltas:
                st.subheader("Itens com Estoque Insuficiente")
                df_f = pd.DataFrame(faltas)
                c1,c2,c3 = st.columns(3)
                with c1: st.metric("Total faltantes", len(df_f))
                with c2: st.metric("Unidades faltando", int(df_f['falta'].sum()))
                with c3: st.metric("Componentes de kit", int((df_f['tipo']=='Componente de Kit').sum()))
                view = df_f[['kit_original','codigo_componente','nome','estoque_atual','qtd_necessaria','falta','tipo']].copy()
                view.columns = ['Kit Original','Código','Produto','Estoque Atual','Qtd Necessária','Falta','Tipo']
                st.dataframe(view, use_container_width=True, height=500)
                st.download_button(
                    "📥 Baixar Relatório de Faltantes (CSV)",
                    view.to_csv(index=False, encoding='utf-8-sig'),
                    file_name=f"relatorio_faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            else:
                st.success("Todos os produtos têm estoque suficiente!")
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")

# ======================
# Footer
# ======================
st.markdown("---")
fc1, fc2, fc3 = st.columns(3)
with fc1:
    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()
with fc2:
    st.write(f"**Última atualização:** {datetime.now().strftime('%H:%M:%S')}")
with fc3:
    st.write(f"**Filtros ativos:** {categoria_filtro} | {status_filtro} | {'SIMULAÇÃO' if SIMULACAO else 'PRODUÇÃO'}")
