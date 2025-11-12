import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO, BytesIO
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
    """
    Recebe algo como '1,2, 3' ou '1.0, nan, 2' (str/float/None)
    e devolve [1, 2, 3]. Ignora nulos/NaN/vazios.
    """
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
# Configuração da página
# ======================
st.set_page_config(
    page_title="Estoque Cockpit - Silva Holding",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URLs
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"

# 🔁 USE O DEPLOYMENT NOVO (o que você publicou agora):
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

        # Garantir colunas necessárias
        required_cols = ['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max']
        for col in required_cols:
            if col not in df.columns:
                if col == 'estoque_max':
                    df[col] = df.get('estoque_min', 0) * 2  # Default: 2x o mínimo
                else:
                    df[col] = 0

        # Converter para numérico
        df['estoque_atual'] = pd.to_numeric(df['estoque_atual'], errors='coerce').fillna(0)
        df['estoque_min'] = pd.to_numeric(df['estoque_min'], errors='coerce').fillna(0)
        df['estoque_max'] = pd.to_numeric(df['estoque_max'], errors='coerce').fillna(0)

        # Blindagem extra para colunas de kits
        for col in ['componentes', 'quantidades', 'eh_kit']:
            if col not in df.columns:
                df[col] = ''
            else:
                df[col] = df[col].astype(str).fillna('')

        return df

    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
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
# Movimentação (Webhook)
# ======================
def movimentar_estoque(codigo, quantidade, tipo, colaborador):
    try:
        dados = {
            'codigo': str(codigo).strip(),
            'quantidade': safe_int(quantidade, 0),
            'tipo': tipo,
            'colaborador': colaborador
        }
        response = requests.post(WEBHOOK_URL, json=dados, timeout=15)
        # Se o Apps Script retornar algo não-JSON, protege:
        try:
            return response.json()
        except Exception:
            return {'success': False, 'message': f'Resposta inesperada do servidor: {response.text[:200]}'}
    except Exception as e:
        return {'success': False, 'message': f'Erro: {str(e)}'}

# ======================
# Expandir kits
# ======================
def expandir_kits(df_fatura, produtos_df):
    """
    Expande produtos que são kits em seus componentes individuais.
    Converte quantidades de forma segura (ignora NaN / vazio).
    """
    kits_dict = {}
    for _, row in produtos_df.iterrows():
        eh_kit = str(row.get('eh_kit', '')).strip().lower()
        if eh_kit == 'sim':
            codigo = str(row.get('codigo', '')).strip().upper()
            if not codigo:
                continue
            componentes_str = row.get('componentes', '')
            quantidades_str = row.get('quantidades', '')
            componentes = [c.strip().upper() for c in str(componentes_str).split(",") if c and c.strip()]
            quantidades = parse_int_list(quantidades_str)
            if componentes and quantidades and len(componentes) == len(quantidades):
                kits_dict[codigo] = list(zip(componentes, quantidades))

    if not kits_dict:
        return df_fatura

    linhas_expandidas = []
    for _, row in df_fatura.iterrows():
        codigo_upper = str(row['codigo']).strip().upper()
        quantidade_kit = safe_int(row.get('quantidade', 0), 0)
        if codigo_upper in kits_dict:
            for componente_codigo, componente_qtd in kits_dict[codigo_upper]:
                linhas_expandidas.append({
                    'codigo': componente_codigo,
                    'quantidade': quantidade_kit * safe_int(componente_qtd, 0)
                })
        else:
            linhas_expandidas.append({
                'codigo': str(row['codigo']).strip(),
                'quantidade': quantidade_kit
            })

    df_expandido = pd.DataFrame(linhas_expandidas)
    df_expandido = df_expandido.groupby('codigo', as_index=False)['quantidade'].sum()
    return df_expandido

# ======================
# Processar faturamento
# ======================
def processar_faturamento(arquivo_upload, produtos_df):
    """
    Retorna (produtos_encontrados, produtos_nao_encontrados, erro)
    """
    try:
        nome_arquivo = arquivo_upload.name.lower()

        if nome_arquivo.endswith('.csv'):
            df_fatura = None
            for encoding in ['utf-8', 'utf-8-sig', 'latin1', 'iso-8859-1', 'cp1252', 'windows-1252']:
                try:
                    arquivo_upload.seek(0)
                    df_fatura = pd.read_csv(arquivo_upload, encoding=encoding)
                    if df_fatura is not None and len(df_fatura.columns) > 0:
                        break
                except:
                    continue
            if df_fatura is None:
                return None, None, "Não foi possível ler o arquivo CSV. Tente salvar como UTF-8."
        elif nome_arquivo.endswith('.xlsx'):
            df_fatura = pd.read_excel(arquivo_upload, engine='openpyxl')
        elif nome_arquivo.endswith('.xls'):
            df_fatura = pd.read_excel(arquivo_upload, engine='xlrd')
        else:
            return None, None, "Formato de arquivo não suportado. Use CSV, XLS ou XLSX."

        # Normalizar nomes das colunas
        def normalizar_coluna(nome):
            nome = unicodedata.normalize('NFKD', str(nome)).encode('ASCII', 'ignore').decode('ASCII')
            return nome.lower().strip()

        colunas_normalizadas = {col: normalizar_coluna(col) for col in df_fatura.columns}
        df_fatura.rename(columns=colunas_normalizadas, inplace=True)

        # Verificar colunas
        if 'codigo' not in df_fatura.columns:
            return None, None, f"Arquivo não possui coluna 'Código'. Colunas encontradas: {list(df_fatura.columns)}"
        if 'quantidade' not in df_fatura.columns:
            return None, None, f"Arquivo não possui coluna 'Quantidade'. Colunas encontradas: {list(df_fatura.columns)}"

        # Limpar e preparar dados
        df_fatura['codigo'] = df_fatura['codigo'].astype(str).str.strip()
        df_fatura['quantidade'] = df_fatura['quantidade'].apply(lambda x: safe_int(x, 0)).astype(int)

        # Remover linhas inválidas
        df_fatura = df_fatura[(df_fatura['codigo'] != '') & (df_fatura['quantidade'] > 0)]

        # Agrupar duplicados
        df_fatura = df_fatura.groupby('codigo', as_index=False)['quantidade'].sum().reset_index(drop=True)

        # Expandir kits
        df_fatura = expandir_kits(df_fatura, produtos_df)

        # Dicionário de estoque
        codigos_estoque = set(produtos_df['codigo'].str.strip().str.upper())
        df_fatura['codigo_upper'] = df_fatura['codigo'].str.upper()
        df_fatura['encontrado'] = df_fatura['codigo_upper'].isin(codigos_estoque)

        produtos_encontrados = df_fatura[df_fatura['encontrado']].copy().reset_index(drop=True)
        produtos_nao_encontrados = df_fatura[~df_fatura['encontrado']].copy().reset_index(drop=True)

        # Enriquecer encontrados
        if not produtos_encontrados.empty:
            estoque_dict = {}
            for _, row in produtos_df.iterrows():
                codigo_upper = str(row['codigo']).strip().upper()
                estoque_dict[codigo_upper] = {
                    'nome': row.get('nome', 'N/A'),
                    'estoque_atual': row.get('estoque_atual', 0)
                }

            produtos_encontrados['nome'] = produtos_encontrados['codigo_upper'].map(
                lambda x: estoque_dict.get(x, {}).get('nome', 'N/A')
            )
            produtos_encontrados['estoque_atual'] = produtos_encontrados['codigo_upper'].map(
                lambda x: estoque_dict.get(x, {}).get('estoque_atual', 0)
            )

            # Garantir numéricos
            produtos_encontrados['estoque_atual'] = pd.to_numeric(produtos_encontrados['estoque_atual'], errors='coerce').fillna(0)
            produtos_encontrados['quantidade'] = pd.to_numeric(produtos_encontrados['quantidade'], errors='coerce').fillna(0)

            produtos_encontrados['estoque_final'] = produtos_encontrados['estoque_atual'] - produtos_encontrados['quantidade']

        return produtos_encontrados, produtos_nao_encontrados, None

    except Exception as e:
        return None, None, f"Erro ao processar arquivo: {str(e)}"

# ======================
# CSS
# ======================
st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
        margin: 0.5rem 0;
    }
    .status-card {
        padding: 1rem;
        border-radius: 8px;
        margin: 0.3rem 0;
        border-left: 4px solid;
    }
    .critico { border-color: #ff4444; background: #ffe6e6; }
    .baixo { border-color: #ffaa00; background: #fff8e6; }
    .ok { border-color: #00aa00; background: #e6ffe6; }
    .excesso { border-color: #0088ff; background: #e6f3ff; }
    .cockpit-header {
        background: linear-gradient(90deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 1rem;
        border-radius: 10px;
        text-align: center;
        margin-bottom: 1rem;
    }
    .warning-box {
        background: #fff3cd;
        border-left: 4px solid #ffc107;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .success-box {
        background: #d4edda;
        border-left: 4px solid #28a745;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
    .error-box {
        background: #f8d7da;
        border-left: 4px solid #dc3545;
        padding: 1rem;
        border-radius: 5px;
        margin: 1rem 0;
    }
</style>
""", unsafe_allow_html=True)

# ======================
# Header
# ======================
st.markdown("""
<div class="cockpit-header">
    <h1> COCKPIT DE CONTROLE - SILVA HOLDING</h1>
    <p>"Se parar para sentir o perfume das rosas, vem um caminhão e te atropela"</p>
</div>
""", unsafe_allow_html=True)

# ======================
# Dados base
# ======================
produtos_df = carregar_produtos()

if produtos_df.empty:
    st.error(" Não foi possível carregar os dados da planilha")
    st.stop()

# Semáforos e métricas derivadas
produtos_df['semaforo'], produtos_df['status'], produtos_df['cor'] = zip(*produtos_df.apply(
    lambda row: calcular_semaforo(row['estoque_atual'], row['estoque_min'], row['estoque_max']), axis=1
))
produtos_df['falta_para_min'] = (produtos_df['estoque_min'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['falta_para_max'] = (produtos_df['estoque_max'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['excesso_sobre_max'] = (produtos_df['estoque_atual'] - produtos_df['estoque_max']).clip(lower=0)
produtos_df['diferenca_min_max'] = produtos_df['estoque_max'] - produtos_df['estoque_min']

# ======================
# Sidebar
# ======================
st.sidebar.header("🎛️ CONTROLES DE VOO")

categorias = ['Todas'] + sorted(produtos_df['categoria'].unique().tolist())
categoria_filtro = st.sidebar.selectbox("📂 Categoria:", categorias)

status_opcoes = ['Todos', 'CRÍTICO', 'BAIXO', 'OK', 'EXCESSO']
status_filtro = st.sidebar.selectbox("🚦 Status:", status_opcoes)

tipo_analise = st.sidebar.radio(
    " Tipo de Análise:",
    ["Visão Geral", "Análise Mín/Máx", "Movimentação", "Baixa por Faturamento", "Histórico de Baixas", "Relatório de Faltantes"]
)

# Aplicar filtros
df_filtrado = produtos_df.copy()
if categoria_filtro != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['categoria'] == categoria_filtro]
if status_filtro != 'Todos':
    df_filtrado = df_filtrado[df_filtrado['status'] == status_filtro]

# ======================
# Visão Geral
# ======================
if tipo_analise == "Visão Geral":
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        total_produtos = len(df_filtrado)
        st.markdown(f"""
        <div class="metric-card">
            <h3> PRODUTOS</h3>
            <h2>{total_produtos}</h2>
        </div>
        """, unsafe_allow_html=True)

    with col2:
        estoque_total = int(df_filtrado['estoque_atual'].sum())
        st.markdown(f"""
        <div class="metric-card">
            <h3> ESTOQUE TOTAL</h3>
            <h2>{estoque_total:,}</h2>
        </div>
        """, unsafe_allow_html=True)

    with col3:
        criticos = len(df_filtrado[df_filtrado['status'] == 'CRÍTICO'])
        st.markdown(f"""
        <div class="metric-card">
            <h3> CRÍTICOS</h3>
            <h2>{criticos}</h2>
        </div>
        """, unsafe_allow_html=True)

    with col4:
        baixos = len(df_filtrado[df_filtrado['status'] == 'BAIXO'])
        st.markdown(f"""
        <div class="metric-card">
            <h3> BAIXOS</h3>
            <h2>{baixos}</h2>
        </div>
        """, unsafe_allow_html=True)

    with col5:
        ok_count = len(df_filtrado[df_filtrado['status'] == 'OK'])
        st.markdown(f"""
        <div class="metric-card">
            <h3> OK</h3>
            <h2>{ok_count}</h2>
        </div>
        """, unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Distribuição por Status")
        status_counts = df_filtrado['status'].value_counts()
        fig_pie = px.pie(
            values=status_counts.values,
            names=status_counts.index,
            color_discrete_map={
                'CRÍTICO': '#ff4444',
                'BAIXO': '#ffaa00',
                'OK': '#00aa00',
                'EXCESSO': '#0088ff'
            }
        )
        fig_pie.update_layout(height=300)
        st.plotly_chart(fig_pie, use_container_width=True)

    with col2:
        st.subheader("📈 Estoque por Categoria")
        cat_estoque = df_filtrado.groupby('categoria')['estoque_atual'].sum().sort_values(ascending=False)
        fig_bar = px.bar(
            x=cat_estoque.index,
            y=cat_estoque.values,
            color=cat_estoque.values,
            color_continuous_scale='viridis'
        )
        fig_bar.update_layout(height=300, showlegend=False)
        st.plotly_chart(fig_bar, use_container_width=True)

    st.subheader("🚨 PRODUTOS EM SITUAÇÃO CRÍTICA")
    produtos_criticos = df_filtrado[df_filtrado['status'].isin(['CRÍTICO', 'BAIXO'])].sort_values('estoque_atual')

    if not produtos_criticos.empty:
        for _, produto in produtos_criticos.head(10).iterrows():
            status_class = produto['status'].lower()
            st.markdown(f"""
            <div class="status-card {status_class}">
                <strong>{produto['semaforo']} {produto['codigo']}</strong> - {produto['nome']}<br>
                <small> Atual: {int(produto['estoque_atual'])} | Mínimo: {int(produto['estoque_min'])} | 
                Falta: {int(produto['falta_para_min'])}</small>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success(" Nenhum produto em situação crítica!")

# ======================
# Análise Mín/Máx
# ======================
elif tipo_analise == "Análise Mín/Máx":
    st.subheader(" ANÁLISE ESTOQUE MÍNIMO/MÁXIMO")

    col1, col2 = st.columns(2)
    with col1:
        analise_tipo = st.selectbox(
            "Tipo de Análise:",
            ["Falta para Mínimo", "Falta para Máximo", "Excesso sobre Máximo", "Diferença Mín-Máx"]
        )

    with col2:
        mostrar_apenas_com_diferenca = st.checkbox("Mostrar apenas com diferença > 0", value=True)

    df_analise = df_filtrado.copy()

    if analise_tipo == "Falta para Mínimo":
        coluna_analise = 'falta_para_min'
        titulo_coluna = 'Falta p/ Mín'
        if mostrar_apenas_com_diferenca:
            df_analise = df_analise[df_analise['falta_para_min'] > 0]
    elif analise_tipo == "Falta para Máximo":
        coluna_analise = 'falta_para_max'
        titulo_coluna = 'Falta p/ Máx'
        if mostrar_apenas_com_diferenca:
            df_analise = df_analise[df_analise['falta_para_max'] > 0]
    elif analise_tipo == "Excesso sobre Máximo":
        coluna_analise = 'excesso_sobre_max'
        titulo_coluna = 'Excesso s/ Máx'
        if mostrar_apenas_com_diferenca:
            df_analise = df_analise[df_analise['excesso_sobre_max'] > 0]
    else:
        coluna_analise = 'diferenca_min_max'
        titulo_coluna = 'Diferença Mín-Máx'
        if mostrar_apenas_com_diferenca:
            df_analise = df_analise[df_analise['diferenca_min_max'] > 0]

    if not df_analise.empty:
        st.write(f"**{len(df_analise)} produtos encontrados**")
        tabela_exibicao = df_analise[['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max', coluna_analise, 'status']].copy()
        tabela_exibicao.columns = ['Código', 'Produto', 'Categoria', 'Atual', 'Mínimo', 'Máximo', titulo_coluna, 'Status']

        for col in ['Atual', 'Mínimo', 'Máximo', titulo_coluna]:
            tabela_exibicao[col] = pd.to_numeric(tabela_exibicao[col], errors='coerce').fillna(0).astype(int)

        tabela_exibicao = tabela_exibicao.sort_values(titulo_coluna, ascending=False)
        st.dataframe(tabela_exibicao, use_container_width=True, height=400)

        csv = tabela_exibicao.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 Baixar Relatório CSV",
            data=csv,
            file_name=f"analise_{analise_tipo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

        if len(df_analise) > 0:
            st.subheader(f" Top 20 - {analise_tipo}")
            top_20 = df_analise.nlargest(20, coluna_analise)
            fig = px.bar(
                top_20,
                x=coluna_analise,
                y='codigo',
                orientation='h',
                color='status',
                title=f"Top 20 - {analise_tipo}",
                color_discrete_map={
                    'CRÍTICO': '#ff4444',
                    'BAIXO': '#ffaa00',
                    'OK': '#00aa00',
                    'EXCESSO': '#0088ff'
                }
            )
            fig.update_layout(height=400)
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("ℹ️ Nenhum produto encontrado com os critérios selecionados")

# ======================
# Movimentação manual
# ======================
elif tipo_analise == "Movimentação":
    st.subheader(" MOVIMENTAÇÃO DE ESTOQUE")

    colaboradores = ['Pericles', 'Maria', 'Camila', 'Cris VantiStella']
    colaborador = st.selectbox("👤 Colaborador:", colaboradores)

    busca = st.text_input("🔍 Buscar produto:", placeholder="Digite código ou nome...")

    if busca and len(busca) >= 2:
        produtos_encontrados = df_filtrado[
            df_filtrado['codigo'].str.contains(busca, case=False, na=False) |
            df_filtrado['nome'].str.contains(busca, case=False, na=False)
        ]

        if not produtos_encontrados.empty:
            st.write(f"**{len(produtos_encontrados)} produto(s) encontrado(s):**")

            for _, produto in produtos_encontrados.head(5).iterrows():
                with st.expander(f"{produto['semaforo']} {produto['codigo']} - {produto['nome']}"):
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        st.metric("Estoque Atual", f"{int(produto['estoque_atual'])}")
                        st.metric("Estoque Mínimo", f"{int(produto['estoque_min'])}")
                        st.metric("Estoque Máximo", f"{int(produto['estoque_max'])}")

                    with col2:
                        st.write("**ENTRADA**")
                        qtd_entrada = st.number_input("Quantidade:", min_value=1, value=1, key=f"ent_{produto['codigo']}")
                        if st.button("+ Entrada", key=f"btn_ent_{produto['codigo']}"):
                            resultado = movimentar_estoque(produto['codigo'], qtd_entrada, 'entrada', colaborador)
                            if resultado.get('success'):
                                st.success(f" Entrada realizada! Novo estoque: {resultado.get('novo_estoque')}")
                                st.rerun()
                            else:
                                st.error(f" {resultado.get('message', 'Erro desconhecido')}")

                    with col3:
                        st.write("**SAÍDA**")
                        max_saida = max(1, int(produto['estoque_atual']))
                        qtd_saida = st.number_input("Quantidade:", min_value=1, max_value=max_saida, value=1, key=f"sai_{produto['codigo']}")
                        if st.button("- Saída", key=f"btn_sai_{produto['codigo']}"):
                            resultado = movimentar_estoque(produto['codigo'], qtd_saida, 'saida', colaborador)
                            if resultado.get('success'):
                                st.success(f" Saída realizada! Novo estoque: {resultado.get('novo_estoque')}")
                                st.rerun()
                            else:
                                st.error(f" {resultado.get('message', 'Erro desconhecido')}")
        else:
            st.warning(" Nenhum produto encontrado")
    elif not busca:
        st.info(" Digite pelo menos 2 caracteres para buscar produtos")

# ======================
# Baixa por Faturamento
# ======================
elif tipo_analise == "Baixa por Faturamento":
    st.subheader(" BAIXA POR FATURAMENTO")

    st.markdown("""
    <div class="success-box">
        <strong>ℹ️ Como funciona:</strong><br>
        1. Faça upload do arquivo de faturamento (CSV, XLS ou XLSX)<br>
        2. O sistema vai identificar quais produtos existem no estoque<br>
        3. Produtos encontrados: baixa será aplicada (permite estoque negativo)<br>
        4. Produtos NÃO encontrados: serão listados para cadastro posterior<br>
        5. Revise o preview e confirme a operação
    </div>
    """, unsafe_allow_html=True)

    colaboradores = ['Pericles', 'Maria', 'Camila', 'Cris VantiStella']
    colaborador_fatura = st.selectbox("👤 Colaborador responsável:", colaboradores, key="colab_fatura")

    arquivo_fatura = st.file_uploader(
        "📁 Selecione o arquivo de faturamento:",
        type=['csv', 'xls', 'xlsx'],
        help="Arquivo deve conter colunas 'Código' e 'Quantidade'"
    )

    if arquivo_fatura is not None:
        with st.spinner(" Processando arquivo..."):
            produtos_encontrados, produtos_nao_encontrados, erro = processar_faturamento(arquivo_fatura, produtos_df)

        if erro:
            st.error(f" {erro}")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                total_linhas = len(produtos_encontrados) + len(produtos_nao_encontrados)
                st.metric(" Total de Linhas", total_linhas)
            with col2:
                st.metric(" Produtos Encontrados", len(produtos_encontrados))
            with col3:
                st.metric(" Produtos NÃO Encontrados", len(produtos_nao_encontrados))

            if not produtos_nao_encontrados.empty:
                st.markdown("---")
                st.markdown("""
                <div class="error-box">
                    <strong> ATENÇÃO: Produtos não encontrados no cadastro</strong><br>
                    Os produtos abaixo NÃO serão baixados do estoque. Você precisa cadastrá-los primeiro.
                </div>
                """, unsafe_allow_html=True)

                tabela_nao_encontrados = produtos_nao_encontrados[['codigo', 'quantidade']].copy()
                tabela_nao_encontrados.columns = ['Código', 'Quantidade Solicitada']
                st.dataframe(tabela_nao_encontrados, use_container_width=True, height=200)

                csv_faltantes = tabela_nao_encontrados.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Baixar Relatório de Códigos Faltantes",
                    data=csv_faltantes,
                    file_name=f"codigos_faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    type="primary"
                )

            if not produtos_encontrados.empty:
                st.markdown("---")
                st.subheader(" Preview da Baixa de Estoque")

                st.markdown("""
                <div class="warning-box">
                    <strong> Importante:</strong> Produtos com estoque zerado terão estoque NEGATIVO após a baixa.
                    Isso indica que você precisa dar entrada manual posteriormente.
                </div>
                """, unsafe_allow_html=True)

                preview_df = produtos_encontrados[['codigo', 'nome', 'estoque_atual', 'quantidade', 'estoque_final']].copy()
                preview_df.columns = ['Código', 'Produto', 'Estoque Atual', 'Qtd a Baixar', 'Estoque Final']

                for col in ['Estoque Atual', 'Qtd a Baixar', 'Estoque Final']:
                    preview_df[col] = pd.to_numeric(preview_df[col], errors='coerce').fillna(0).astype(int)

                preview_df['Status'] = preview_df['Estoque Final'].apply(
                    lambda x: ' Negativo' if x < 0 else (' Zerado' if x == 0 else ' OK')
                )

                st.dataframe(preview_df, use_container_width=True, height=400)

                col1, col2, col3 = st.columns(3)
                with col1:
                    total_baixar = int(preview_df['Qtd a Baixar'].sum())
                    st.metric(" Total a Baixar", f"{total_baixar:,}")
                with col2:
                    ficarao_negativos = len(preview_df[preview_df['Estoque Final'] < 0])
                    st.metric(" Ficarão Negativos", ficarao_negativos)
                with col3:
                    ficarao_zerados = len(preview_df[preview_df['Estoque Final'] == 0])
                    st.metric(" Ficarão Zerados", ficarao_zerados)

                st.markdown("---")
                col1, col2, col3 = st.columns([1, 2, 1])

                with col2:
                    if st.button(" CONFIRMAR E APLICAR BAIXAS", type="primary", use_container_width=True):
                        sucesso_count = 0
                        erro_count = 0
                        resultados = []

                        progress_bar = st.progress(0)
                        status_text = st.empty()

                        total = len(produtos_encontrados)

                        for idx, row in produtos_encontrados.iterrows():
                            status_text.text(f"Processando {idx+1}/{total}: {row['codigo']}")

                            resultado = movimentar_estoque(
                                row['codigo'],
                                row['quantidade'],
                                'saida',
                                colaborador_fatura
                            )

                            if resultado.get('success'):
                                sucesso_count += 1
                                resultados.append({
                                    'codigo': row['codigo'],
                                    'nome': row['nome'],
                                    'qtd_baixada': row['quantidade'],
                                    'estoque_anterior': row['estoque_atual'],
                                    'estoque_final': resultado.get('novo_estoque', 'N/A'),
                                    'status': '✅ Sucesso',
                                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'colaborador': colaborador_fatura
                                })
                            else:
                                erro_count += 1
                                resultados.append({
                                    'codigo': row['codigo'],
                                    'nome': row['nome'],
                                    'qtd_baixada': row['quantidade'],
                                    'estoque_anterior': row['estoque_atual'],
                                    'estoque_final': 'N/A',
                                    'status': f"❌ Erro: {resultado.get('message', 'Desconhecido')}",
                                    'data_hora': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                    'colaborador': colaborador_fatura
                                })

                            progress_bar.progress((idx + 1) / total)

                        progress_bar.empty()
                        status_text.empty()

                        st.markdown("---")
                        st.subheader("📄 Relatório de Baixas Realizadas")

                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("✅ Sucessos", sucesso_count)
                        with col2:
                            st.metric("❌ Erros", erro_count)
                        with col3:
                            st.metric("📊 Total Processado", sucesso_count + erro_count)

                        if erro_count == 0:
                            st.success(f"✅ Baixa concluída com sucesso! {sucesso_count} produtos atualizados.")
                        else:
                            st.warning(f"⚠️ Baixa concluída com problemas: {sucesso_count} sucessos, {erro_count} erros.")

                        df_resultados = pd.DataFrame(resultados)
                        df_resultados_display = df_resultados[['codigo', 'nome', 'qtd_baixada', 'estoque_anterior', 'estoque_final', 'status']].copy()
                        df_resultados_display.columns = ['Código', 'Produto', 'Qtd Baixada', 'Estoque Anterior', 'Estoque Final', 'Status']

                        st.dataframe(df_resultados_display, use_container_width=True, height=400)

                        csv_relatorio = df_resultados.to_csv(index=False, encoding='utf-8-sig')
                        st.download_button(
                            label="📥 Baixar Relatório Completo (CSV)",
                            data=csv_relatorio,
                            file_name=f"relatorio_baixas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                            mime="text/csv",
                            type="primary"
                        )

                        st.cache_data.clear()
                        st.balloons()

                        if st.button(" Processar Novo Arquivo"):
                            st.rerun()

# ======================
# Histórico de Baixas
# ======================
elif tipo_analise == "Histórico de Baixas":
    st.title("📊 HISTÓRICO DE BAIXAS POR FATURAMENTO")

    st.markdown("""
    <div class="info-box">
        <strong>📊 Informações do Histórico:</strong><br>
        Esta aba mostra todas as baixas realizadas via faturamento.<br>
        Os dados são carregados da planilha <strong>historico_baixas</strong> no Google Sheets.
    </div>
    """, unsafe_allow_html=True)

    try:
        HISTORICO_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/gviz/tq?tqx=out:csv&sheet=historico_baixas"

        with st.spinner("🔄 Carregando histórico..."):
            try:
                response = requests.get(HISTORICO_URL, timeout=10)
                response.raise_for_status()

                csv_data = StringIO(response.text)
                df_historico = pd.read_csv(csv_data)

                if df_historico.empty:
                    st.info("📄 Nenhuma baixa registrada ainda.")
                else:
                    # 🔧 Coerção segura
                    if 'qtd_baixada' in df_historico.columns:
                        df_historico['qtd_baixada'] = pd.to_numeric(df_historico['qtd_baixada'], errors='coerce').fillna(0)

                    st.markdown("---")
                    st.subheader("📊 Estatísticas Gerais")

                    col1, col2, col3, col4 = st.columns(4)

                    with col1:
                        total_baixas = len(df_historico)
                        st.metric("📊 Total de Baixas", f"{total_baixas:,}")

                    with col2:
                        if 'qtd_baixada' in df_historico.columns:
                            total_unidades = df_historico['qtd_baixada'].sum()
                            st.metric("📦 Total de Unidades", f"{int(total_unidades):,}")
                        else:
                            st.metric("📦 Total de Unidades", "N/A")

                    with col3:
                        if 'colaborador' in df_historico.columns:
                            total_colaboradores = df_historico['colaborador'].nunique()
                            st.metric("👥 Colaboradores", total_colaboradores)
                        else:
                            st.metric("👥 Colaboradores", "N/A")

                    with col4:
                        if 'status' in df_historico.columns:
                            sucessos = len(df_historico[df_historico['status'].astype(str).str.contains('Sucesso', na=False)])
                            st.metric("✅ Taxa de Sucesso", f"{(sucessos/total_baixas*100):.1f}%")
                        else:
                            st.metric("✅ Taxa de Sucesso", "N/A")

                    st.markdown("---")
                    st.subheader("🔍 Filtros")

                    col1, col2, col3 = st.columns(3)

                    with col1:
                        if 'colaborador' in df_historico.columns:
                            colaboradores_hist = ['Todos'] + sorted(df_historico['colaborador'].astype(str).unique().tolist())
                            filtro_colab = st.selectbox("👤 Colaborador:", colaboradores_hist)
                        else:
                            filtro_colab = 'Todos'

                    with col2:
                        if 'status' in df_historico.columns:
                            status_hist = ['Todos', 'Sucesso', 'Erro']
                            filtro_status = st.selectbox("🚦 Status:", status_hist)
                        else:
                            filtro_status = 'Todos'

                    with col3:
                        if 'data_hora' in df_historico.columns:
                            periodo_opcoes = ['Todos', 'Últimas 24h', 'Últimos 7 dias', 'Últimos 30 dias']
                            filtro_periodo = st.selectbox("📅 Período:", periodo_opcoes)
                        else:
                            filtro_periodo = 'Todos'

                    df_filtrado_hist = df_historico.copy()

                    if filtro_colab != 'Todos' and 'colaborador' in df_filtrado_hist.columns:
                        df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['colaborador'] == filtro_colab]

                    if filtro_status != 'Todos' and 'status' in df_filtrado_hist.columns:
                        if filtro_status == 'Sucesso':
                            df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['status'].astype(str).str.contains('Sucesso', na=False)]
                        else:
                            df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['status'].astype(str).str.contains('Erro', na=False)]

                    if filtro_periodo != 'Todos' and 'data_hora' in df_filtrado_hist.columns:
                        df_filtrado_hist['data_hora'] = pd.to_datetime(df_filtrado_hist['data_hora'], errors='coerce')
                        agora = datetime.now()

                        if filtro_periodo == 'Últimas 24h':
                            df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['data_hora'] >= agora - pd.Timedelta(days=1)]
                        elif filtro_periodo == 'Últimos 7 dias':
                            df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['data_hora'] >= agora - pd.Timedelta(days=7)]
                        elif filtro_periodo == 'Últimos 30 dias':
                            df_filtrado_hist = df_filtrado_hist[df_filtrado_hist['data_hora'] >= agora - pd.Timedelta(days=30)]

                    st.markdown("---")
                    st.subheader("📊 Histórico de Baixas")
                    st.dataframe(df_filtrado_hist, use_container_width=True, height=500)

                    csv_export = df_filtrado_hist.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 Baixar Histórico Filtrado (CSV)",
                        data=csv_export,
                        file_name=f"historico_baixas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        type="primary"
                    )

            except requests.exceptions.HTTPError:
                st.warning("""
                ⚠️ **Aba de histórico não encontrada!**
                
                Para habilitar o histórico de baixas:
                
                1. Abra a planilha do Google Sheets
                2. Crie uma nova aba chamada **historico_baixas**
                3. Adicione as colunas: `codigo`, `nome`, `qtd_baixada`, `estoque_anterior`, `estoque_final`, `status`, `data_hora`, `colaborador`
                4. O sistema irá registrar automaticamente as próximas baixas
                """)
    except Exception as e:
        st.error(f"❌ Erro ao carregar histórico: {str(e)}")

# ======================
# Relatório de Faltantes
# ======================
elif tipo_analise == "Relatório de Faltantes":
    st.title(" RELATÓRIO DE PRODUTOS FALTANTES")

    st.markdown("""
    <div class="info-box">
        <strong> Como funciona:</strong>
        <ol>
            <li>Faça upload do arquivo de vendas (CSV, XLS ou XLSX)</li>
            <li>O sistema verifica quais produtos têm estoque insuficiente</li>
            <li>Para kits, expande em componentes individuais e verifica cada um</li>
            <li>Gera relatório com produtos/componentes faltantes</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")

    st.subheader(" Selecione o arquivo de vendas:")
    arquivo_vendas = st.file_uploader(
        "Arraste o arquivo ou clique para selecionar",
        type=['csv', 'xls', 'xlsx'],
        help="Arquivo deve conter colunas: codigo e quantidade"
    )

    if arquivo_vendas:
        try:
            nome_arquivo = arquivo_vendas.name.lower()

            if nome_arquivo.endswith('.csv'):
                df_vendas = pd.read_csv(arquivo_vendas, encoding='latin1')
            elif nome_arquivo.endswith('.xlsx'):
                df_vendas = pd.read_excel(arquivo_vendas, engine='openpyxl')
            elif nome_arquivo.endswith('.xls'):
                df_vendas = pd.read_excel(arquivo_vendas, engine='xlrd')

            df_vendas = df_vendas.reset_index(drop=True)
            df_vendas.columns = df_vendas.columns.str.lower().str.strip()

            if 'codigo' not in df_vendas.columns or 'quantidade' not in df_vendas.columns:
                st.error(f" Arquivo deve conter as colunas 'codigo' e 'quantidade'. Colunas encontradas: {list(df_vendas.columns)}")
            else:
                df_vendas['codigo'] = df_vendas['codigo'].astype(str).str.strip()
                df_vendas['quantidade'] = df_vendas['quantidade'].apply(lambda x: safe_int(x, 0)).astype(int)

                df_vendas = df_vendas.groupby('codigo', as_index=False)['quantidade'].sum()

                st.success(f" Arquivo carregado: {len(df_vendas)} produtos")

                faltantes = []

                for idx, row in df_vendas.iterrows():
                    codigo = row['codigo']
                    qtd_vendida = safe_int(row['quantidade'], 0)

                    produto = produtos_df[produtos_df['codigo'].str.upper() == codigo.upper()]

                    if not produto.empty:
                        produto = produto.iloc[0]
                        eh_kit = str(produto.get('eh_kit', '')).strip().lower() == 'sim'

                        if eh_kit:
                            componentes_str = str(produto.get('componentes', ''))
                            quantidades_str = str(produto.get('quantidades', ''))

                            componentes = [c.strip().upper() for c in componentes_str.split(',') if c and c.strip()]
                            quantidades = parse_int_list(quantidades_str)

                            for comp_codigo, comp_qtd_kit in zip(componentes, quantidades):
                                qtd_necessaria = safe_int(qtd_vendida, 0) * safe_int(comp_qtd_kit, 0)

                                comp_produto = produtos_df[produtos_df['codigo'].str.upper() == comp_codigo.upper()]
                                if not comp_produto.empty:
                                    comp_produto = comp_produto.iloc[0]
                                    estoque_atual = comp_produto.get('estoque_atual', 0)

                                    if estoque_atual < qtd_necessaria:
                                        faltantes.append({
                                            'kit_original': codigo,
                                            'codigo_componente': comp_codigo,
                                            'nome': comp_produto.get('nome', ''),
                                            'estoque_atual': safe_int(estoque_atual, 0),  # ✅ fix scalar fillna
                                            'qtd_necessaria': int(qtd_necessaria),
                                            'falta': int(qtd_necessaria - safe_int(estoque_atual, 0)),
                                            'tipo': 'Componente de Kit'
                                        })
                                else:
                                    faltantes.append({
                                        'kit_original': codigo,
                                        'codigo_componente': comp_codigo,
                                        'nome': 'NÃO CADASTRADO',
                                        'estoque_atual': 0,
                                        'qtd_necessaria': int(qtd_necessaria),
                                        'falta': int(qtd_necessaria),
                                        'tipo': 'Componente NÃO Cadastrado'
                                    })
                        else:
                            estoque_atual = produto.get('estoque_atual', 0)
                            if safe_int(estoque_atual, 0) < qtd_vendida:
                                faltantes.append({
                                    'kit_original': '-',
                                    'codigo_componente': codigo,
                                    'nome': produto.get('nome', ''),
                                    'estoque_atual': safe_int(estoque_atual, 0),  # ✅ fix scalar fillna
                                    'qtd_necessaria': int(qtd_vendida),
                                    'falta': int(qtd_vendida - safe_int(estoque_atual, 0)),
                                    'tipo': 'Produto Normal'
                                })
                    else:
                        faltantes.append({
                            'kit_original': '-',
                            'codigo_componente': codigo,
                            'nome': 'NÃO CADASTRADO',
                            'estoque_atual': 0,
                            'qtd_necessaria': int(qtd_vendida),
                            'falta': int(qtd_vendida),
                            'tipo': 'Produto NÃO Cadastrado'
                        })

                st.markdown("---")

                if faltantes:
                    st.subheader(" Produtos/Componentes com Estoque Insuficiente")
                    df_faltantes = pd.DataFrame(faltantes)

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(" Total de Itens Faltantes", len(df_faltantes))
                    with col2:
                        total_falta = df_faltantes['falta'].sum()
                        st.metric(" Total de Unidades Faltando", f"{total_falta:,}")
                    with col3:
                        componentes_kit = len(df_faltantes[df_faltantes['tipo'] == 'Componente de Kit'])
                        st.metric(" Componentes de Kit", componentes_kit)

                    st.markdown("---")

                    tabela_faltantes = df_faltantes[['kit_original', 'codigo_componente', 'nome', 'estoque_atual', 'qtd_necessaria', 'falta', 'tipo']].copy()
                    tabela_faltantes.columns = ['Kit Original', 'Código', 'Produto', 'Estoque Atual', 'Qtd Necessária', 'Falta', 'Tipo']

                    st.dataframe(tabela_faltantes, use_container_width=True, height=400)

                    st.markdown("---")
                    csv_relatorio = tabela_faltantes.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label=" Baixar Relatório de Faltantes (CSV)",
                        data=csv_relatorio,
                        file_name=f"relatorio_faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
                else:
                    st.success(" Todos os produtos têm estoque suficiente!")
                    st.balloons()

        except Exception as e:
            st.error(f" Erro ao processar arquivo: {str(e)}")

# ======================
# Footer
# ======================
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button(" Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()

with col2:
    st.write(f"**Última atualização:** {datetime.now().strftime('%H:%M:%S')}")

with col3:
    st.write(f"**Filtros ativos:** {categoria_filtro} | {status_filtro}")
