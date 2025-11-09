import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO, BytesIO

# Configuração da página
st.set_page_config(
    page_title="🛩️ Estoque Cockpit - Silva Holding",
    page_icon="🛩️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# URLs
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxDAmK8RaizGAJMBbIr_urPVP-REsD6zVZAFQI6tQPydWtxllXY2ccNPpEpITFXZ9hp/exec"

# Função para carregar produtos
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
        
        return df
        
    except Exception as e:
        st.error(f"Erro ao carregar dados: {str(e)}")
        return pd.DataFrame()

# Função para calcular semáforo
def calcular_semaforo(estoque_atual, estoque_min, estoque_max):
    # Crítico = ABAIXO do mínimo (não igual)
    if estoque_atual < estoque_min:
        return "🔴", "CRÍTICO", "#ff4444"
    elif estoque_atual <= estoque_min * 1.2:  # Até 20% acima do mínimo
        return "🟡", "BAIXO", "#ffaa00"
    elif estoque_atual > estoque_max:
        return "🔵", "EXCESSO", "#0088ff"
    else:
        return "🟢", "OK", "#00aa00"

# Função para movimentar estoque
def movimentar_estoque(codigo, quantidade, tipo, colaborador):
    try:
        dados = {
            'codigo': codigo,
            'quantidade': int(quantidade),
            'tipo': tipo,
            'colaborador': colaborador
        }
        
        response = requests.post(WEBHOOK_URL, json=dados, timeout=10)
        return response.json()
        
    except Exception as e:
        return {'success': False, 'message': f'Erro: {str(e)}'}

# Função para processar arquivo de faturamento
def processar_faturamento(arquivo_upload, produtos_df):
    """
    Processa arquivo de faturamento e retorna:
    - produtos_encontrados: DataFrame com produtos que existem no estoque
    - produtos_nao_encontrados: DataFrame com produtos que NÃO existem no estoque
    """
    try:
        # Ler arquivo baseado na extensão
        nome_arquivo = arquivo_upload.name.lower()
        
        if nome_arquivo.endswith('.csv'):
            # Tentar diferentes encodings para CSV
            for encoding in ['latin1', 'utf-8', 'iso-8859-1', 'cp1252']:
                try:
                    df_fatura = pd.read_csv(arquivo_upload, encoding=encoding)
                    break
                except:
                    continue
        elif nome_arquivo.endswith('.xlsx'):
            df_fatura = pd.read_excel(arquivo_upload, engine='openpyxl')
        elif nome_arquivo.endswith('.xls'):
            df_fatura = pd.read_excel(arquivo_upload, engine='xlrd')
        else:
            return None, None, "Formato de arquivo não suportado. Use CSV, XLS ou XLSX."
        
        # Verificar se tem as colunas necessárias
        if 'Código' not in df_fatura.columns and 'codigo' not in df_fatura.columns:
            return None, None, "Arquivo não possui coluna 'Código' ou 'codigo'"
        
        if 'Quantidade' not in df_fatura.columns and 'quantidade' not in df_fatura.columns:
            return None, None, "Arquivo não possui coluna 'Quantidade' ou 'quantidade'"
        
        # Normalizar nomes das colunas
        df_fatura.columns = df_fatura.columns.str.lower()
        
        # Renomear se necessário
        if 'código' in df_fatura.columns:
            df_fatura.rename(columns={'código': 'codigo'}, inplace=True)
        
        # Limpar e preparar dados
        df_fatura['codigo'] = df_fatura['codigo'].astype(str).str.strip()
        df_fatura['quantidade'] = pd.to_numeric(df_fatura['quantidade'], errors='coerce').fillna(0).astype(int)
        
        # Remover linhas sem código ou quantidade
        df_fatura = df_fatura[(df_fatura['codigo'] != '') & (df_fatura['quantidade'] > 0)]
        
        # Resetar índice para evitar duplicatas
        df_fatura = df_fatura.reset_index(drop=True)
        
        # Criar dicionário de códigos do estoque para busca rápida
        codigos_estoque = set(produtos_df['codigo'].str.strip().str.upper())
        
        # Separar produtos encontrados e não encontrados
        df_fatura['codigo_upper'] = df_fatura['codigo'].str.upper()
        df_fatura['encontrado'] = df_fatura['codigo_upper'].isin(codigos_estoque)
        
        produtos_encontrados = df_fatura[df_fatura['encontrado']].copy()
        produtos_nao_encontrados = df_fatura[~df_fatura['encontrado']].copy()
        
        # Resetar índices para evitar problemas
        produtos_encontrados = produtos_encontrados.reset_index(drop=True)
        produtos_nao_encontrados = produtos_nao_encontrados.reset_index(drop=True)
        
        # Adicionar informações do estoque aos produtos encontrados
        if not produtos_encontrados.empty:
            # Criar dicionário para merge
            estoque_dict = produtos_df.set_index(produtos_df['codigo'].str.upper()).to_dict('index')
            
            produtos_encontrados['nome'] = produtos_encontrados['codigo_upper'].map(
                lambda x: estoque_dict.get(x, {}).get('nome', 'N/A')
            )
            produtos_encontrados['estoque_atual'] = produtos_encontrados['codigo_upper'].map(
                lambda x: estoque_dict.get(x, {}).get('estoque_atual', 0)
            )
            produtos_encontrados['estoque_final'] = produtos_encontrados['estoque_atual'] - produtos_encontrados['quantidade']
        
        return produtos_encontrados, produtos_nao_encontrados, None
        
    except Exception as e:
        return None, None, f"Erro ao processar arquivo: {str(e)}"

# CSS personalizado para dashboard
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

# Header principal
st.markdown("""
<div class="cockpit-header">
    <h1>🛩️ COCKPIT DE CONTROLE - SILVA HOLDING</h1>
    <p>"Se parar para sentir o perfume das rosas, vem um caminhão e te atropela"</p>
</div>
""", unsafe_allow_html=True)

# Carregar dados
produtos_df = carregar_produtos()

if produtos_df.empty:
    st.error("❌ Não foi possível carregar os dados da planilha")
    st.stop()

# Calcular métricas e semáforos
produtos_df['semaforo'], produtos_df['status'], produtos_df['cor'] = zip(*produtos_df.apply(
    lambda row: calcular_semaforo(row['estoque_atual'], row['estoque_min'], row['estoque_max']), axis=1
))

# Calcular diferenças
produtos_df['falta_para_min'] = (produtos_df['estoque_min'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['falta_para_max'] = (produtos_df['estoque_max'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['excesso_sobre_max'] = (produtos_df['estoque_atual'] - produtos_df['estoque_max']).clip(lower=0)
produtos_df['diferenca_min_max'] = produtos_df['estoque_max'] - produtos_df['estoque_min']

# Sidebar - Controles
st.sidebar.header("🎛️ CONTROLES DE VOO")

# Filtro por categoria
categorias = ['Todas'] + sorted(produtos_df['categoria'].unique().tolist())
categoria_filtro = st.sidebar.selectbox("📂 Categoria:", categorias)

# Filtro por status
status_opcoes = ['Todos', 'CRÍTICO', 'BAIXO', 'OK', 'EXCESSO']
status_filtro = st.sidebar.selectbox("🚦 Status:", status_opcoes)

# Tipo de análise
tipo_analise = st.sidebar.radio(
    "📊 Tipo de Análise:",
    ["Visão Geral", "Análise Mín/Máx", "Movimentação", "Baixa por Faturamento"]
)

# Aplicar filtros
df_filtrado = produtos_df.copy()

if categoria_filtro != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['categoria'] == categoria_filtro]

if status_filtro != 'Todos':
    df_filtrado = df_filtrado[df_filtrado['status'] == status_filtro]

# DASHBOARD PRINCIPAL
if tipo_analise == "Visão Geral":
    
    # Métricas principais
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        total_produtos = len(df_filtrado)
        st.markdown(f"""
        <div class="metric-card">
            <h3>📦 PRODUTOS</h3>
            <h2>{total_produtos}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        estoque_total = int(df_filtrado['estoque_atual'].sum())
        st.markdown(f"""
        <div class="metric-card">
            <h3>📊 ESTOQUE TOTAL</h3>
            <h2>{estoque_total:,}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        criticos = len(df_filtrado[df_filtrado['status'] == 'CRÍTICO'])
        st.markdown(f"""
        <div class="metric-card">
            <h3>🔴 CRÍTICOS</h3>
            <h2>{criticos}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        baixos = len(df_filtrado[df_filtrado['status'] == 'BAIXO'])
        st.markdown(f"""
        <div class="metric-card">
            <h3>🟡 BAIXOS</h3>
            <h2>{baixos}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    with col5:
        ok_count = len(df_filtrado[df_filtrado['status'] == 'OK'])
        st.markdown(f"""
        <div class="metric-card">
            <h3>🟢 OK</h3>
            <h2>{ok_count}</h2>
        </div>
        """, unsafe_allow_html=True)
    
    # Gráficos
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📊 Distribuição por Status")
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
    
    # Lista de produtos críticos
    st.subheader("🚨 PRODUTOS EM SITUAÇÃO CRÍTICA")
    produtos_criticos = df_filtrado[df_filtrado['status'].isin(['CRÍTICO', 'BAIXO'])].sort_values('estoque_atual')
    
    if not produtos_criticos.empty:
        for _, produto in produtos_criticos.head(10).iterrows():
            status_class = produto['status'].lower()
            st.markdown(f"""
            <div class="status-card {status_class}">
                <strong>{produto['semaforo']} {produto['codigo']}</strong> - {produto['nome']}<br>
                <small>📦 Atual: {int(produto['estoque_atual'])} | Mínimo: {int(produto['estoque_min'])} | 
                Falta: {int(produto['falta_para_min'])}</small>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✅ Nenhum produto em situação crítica!")

elif tipo_analise == "Análise Mín/Máx":
    
    st.subheader("📊 ANÁLISE ESTOQUE MÍNIMO/MÁXIMO")
    
    # Opções de análise
    col1, col2 = st.columns(2)
    with col1:
        analise_tipo = st.selectbox(
            "Tipo de Análise:",
            ["Falta para Mínimo", "Falta para Máximo", "Excesso sobre Máximo", "Diferença Mín-Máx"]
        )
    
    with col2:
        mostrar_apenas_com_diferenca = st.checkbox("Mostrar apenas com diferença > 0", value=True)
    
    # Preparar dados baseado na análise
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
    
    else:  # Diferença Mín-Máx
        coluna_analise = 'diferenca_min_max'
        titulo_coluna = 'Diferença Mín-Máx'
        if mostrar_apenas_com_diferenca:
            df_analise = df_analise[df_analise['diferenca_min_max'] > 0]
    
    # Tabela de análise
    if not df_analise.empty:
        st.write(f"**{len(df_analise)} produtos encontrados**")
        
        # Preparar dados para exibição
        tabela_exibicao = df_analise[[
            'codigo', 'nome', 'categoria', 'estoque_atual', 
            'estoque_min', 'estoque_max', coluna_analise, 'status'
        ]].copy()
        
        tabela_exibicao.columns = [
            'Código', 'Produto', 'Categoria', 'Atual', 
            'Mínimo', 'Máximo', titulo_coluna, 'Status'
        ]
        
        # Formatar números
        for col in ['Atual', 'Mínimo', 'Máximo', titulo_coluna]:
            tabela_exibicao[col] = tabela_exibicao[col].astype(int)
        
        # Ordenar por diferença
        tabela_exibicao = tabela_exibicao.sort_values(titulo_coluna, ascending=False)
        
        # Exibir tabela
        st.dataframe(tabela_exibicao, use_container_width=True, height=400)
        
        # Download CSV
        csv = tabela_exibicao.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📥 Baixar Relatório CSV",
            data=csv,
            file_name=f"analise_{analise_tipo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
        
        # Gráfico top 20
        if len(df_analise) > 0:
            st.subheader(f"📊 Top 20 - {analise_tipo}")
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

elif tipo_analise == "Movimentação":
    
    st.subheader("📦 MOVIMENTAÇÃO DE ESTOQUE")
    
    # Colaboradores
    colaboradores = ['Pericles', 'Maria', 'Camila', 'Cris VantiStella']
    colaborador = st.selectbox("👤 Colaborador:", colaboradores)
    
    # Busca de produto
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
                        if st.button("➕ Entrada", key=f"btn_ent_{produto['codigo']}"):
                            resultado = movimentar_estoque(produto['codigo'], qtd_entrada, 'entrada', colaborador)
                            if resultado.get('success'):
                                st.success(f"✅ Entrada realizada! Novo estoque: {resultado.get('novo_estoque')}")
                                st.rerun()
                            else:
                                st.error(f"❌ {resultado.get('message', 'Erro desconhecido')}")
                    
                    with col3:
                        st.write("**SAÍDA**")
                        max_saida = max(1, int(produto['estoque_atual']))
                        qtd_saida = st.number_input("Quantidade:", min_value=1, max_value=max_saida, value=1, key=f"sai_{produto['codigo']}")
                        if st.button("➖ Saída", key=f"btn_sai_{produto['codigo']}"):
                            resultado = movimentar_estoque(produto['codigo'], qtd_saida, 'saida', colaborador)
                            if resultado.get('success'):
                                st.success(f"✅ Saída realizada! Novo estoque: {resultado.get('novo_estoque')}")
                                st.rerun()
                            else:
                                st.error(f"❌ {resultado.get('message', 'Erro desconhecido')}")
        else:
            st.warning("❌ Nenhum produto encontrado")
    
    elif not busca:
        st.info("💡 Digite pelo menos 2 caracteres para buscar produtos")

elif tipo_analise == "Baixa por Faturamento":
    
    st.subheader("📄 BAIXA POR FATURAMENTO")
    
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
    
    # Colaborador
    colaboradores = ['Pericles', 'Maria', 'Camila', 'Cris VantiStella']
    colaborador_fatura = st.selectbox("👤 Colaborador responsável:", colaboradores, key="colab_fatura")
    
    # Upload do arquivo
    arquivo_fatura = st.file_uploader(
        "📁 Selecione o arquivo de faturamento:",
        type=['csv', 'xls', 'xlsx'],
        help="Arquivo deve conter colunas 'Código' e 'Quantidade'"
    )
    
    if arquivo_fatura is not None:
        
        # Processar arquivo
        with st.spinner("🔄 Processando arquivo..."):
            produtos_encontrados, produtos_nao_encontrados, erro = processar_faturamento(arquivo_fatura, produtos_df)
        
        if erro:
            st.error(f"❌ {erro}")
        
        else:
            # Resumo do processamento
            col1, col2, col3 = st.columns(3)
            
            with col1:
                total_linhas = len(produtos_encontrados) + len(produtos_nao_encontrados)
                st.metric("📊 Total de Linhas", total_linhas)
            
            with col2:
                st.metric("✅ Produtos Encontrados", len(produtos_encontrados))
            
            with col3:
                st.metric("❌ Produtos NÃO Encontrados", len(produtos_nao_encontrados))
            
            # PRODUTOS NÃO ENCONTRADOS
            if not produtos_nao_encontrados.empty:
                st.markdown("---")
                st.markdown("""
                <div class="error-box">
                    <strong>⚠️ ATENÇÃO: Produtos não encontrados no cadastro</strong><br>
                    Os produtos abaixo NÃO serão baixados do estoque. Você precisa cadastrá-los primeiro.
                </div>
                """, unsafe_allow_html=True)
                
                # Tabela de não encontrados
                tabela_nao_encontrados = produtos_nao_encontrados[['codigo', 'quantidade']].copy()
                tabela_nao_encontrados.columns = ['Código', 'Quantidade Solicitada']
                
                st.dataframe(tabela_nao_encontrados, use_container_width=True, height=200)
                
                # Download relatório de faltantes
                csv_faltantes = tabela_nao_encontrados.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Baixar Relatório de Códigos Faltantes",
                    data=csv_faltantes,
                    file_name=f"codigos_faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv",
                    type="primary"
                )
            
            # PRODUTOS ENCONTRADOS - PREVIEW
            if not produtos_encontrados.empty:
                st.markdown("---")
                st.subheader("✅ Preview da Baixa de Estoque")
                
                st.markdown("""
                <div class="warning-box">
                    <strong>💡 Importante:</strong> Produtos com estoque zerado terão estoque NEGATIVO após a baixa.
                    Isso indica que você precisa dar entrada manual posteriormente.
                </div>
                """, unsafe_allow_html=True)
                
                # Preparar tabela de preview
                preview_df = produtos_encontrados[['codigo', 'nome', 'estoque_atual', 'quantidade', 'estoque_final']].copy()
                preview_df.columns = ['Código', 'Produto', 'Estoque Atual', 'Qtd a Baixar', 'Estoque Final']
                
                # Formatar números
                for col in ['Estoque Atual', 'Qtd a Baixar', 'Estoque Final']:
                    preview_df[col] = preview_df[col].astype(int)
                
                # Adicionar indicador visual
                preview_df['Status'] = preview_df['Estoque Final'].apply(
                    lambda x: '🔴 Negativo' if x < 0 else ('🟡 Zerado' if x == 0 else '🟢 OK')
                )
                
                # Exibir tabela
                st.dataframe(preview_df, use_container_width=True, height=400)
                
                # Estatísticas
                col1, col2, col3 = st.columns(3)
                with col1:
                    total_baixar = int(preview_df['Qtd a Baixar'].sum())
                    st.metric("📦 Total a Baixar", f"{total_baixar:,}")
                
                with col2:
                    ficarao_negativos = len(preview_df[preview_df['Estoque Final'] < 0])
                    st.metric("🔴 Ficarão Negativos", ficarao_negativos)
                
                with col3:
                    ficarao_zerados = len(preview_df[preview_df['Estoque Final'] == 0])
                    st.metric("🟡 Ficarão Zerados", ficarao_zerados)
                
                # Botão de confirmação
                st.markdown("---")
                col1, col2, col3 = st.columns([1, 2, 1])
                
                with col2:
                    if st.button("✅ CONFIRMAR E APLICAR BAIXAS", type="primary", use_container_width=True):
                        
                        # Aplicar baixas
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
                                    'status': '✅ Sucesso',
                                    'novo_estoque': resultado.get('novo_estoque', 'N/A')
                                })
                            else:
                                erro_count += 1
                                resultados.append({
                                    'codigo': row['codigo'],
                                    'status': f"❌ Erro: {resultado.get('message', 'Desconhecido')}",
                                    'novo_estoque': 'N/A'
                                })
                            
                            progress_bar.progress((idx + 1) / total)
                        
                        progress_bar.empty()
                        status_text.empty()
                        
                        # Mostrar resultado final
                        if erro_count == 0:
                            st.success(f"🎉 Baixa concluída com sucesso! {sucesso_count} produtos atualizados.")
                        else:
                            st.warning(f"⚠️ Baixa concluída com problemas: {sucesso_count} sucessos, {erro_count} erros.")
                        
                        # Mostrar detalhes
                        with st.expander("📋 Ver Detalhes da Operação"):
                            df_resultados = pd.DataFrame(resultados)
                            st.dataframe(df_resultados, use_container_width=True)
                        
                        # Limpar cache e recarregar
                        st.cache_data.clear()
                        st.balloons()
                        
                        # Botão para voltar
                        if st.button("🔄 Processar Novo Arquivo"):
                            st.rerun()

# Footer
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🔄 Atualizar Dados"):
        st.cache_data.clear()
        st.rerun()

with col2:
    st.write(f"**Última atualização:** {datetime.now().strftime('%H:%M:%S')}")

with col3:
    st.write(f"**Filtros ativos:** {categoria_filtro} | {status_filtro}")
