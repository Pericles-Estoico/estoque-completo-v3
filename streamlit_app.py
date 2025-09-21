import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import requests
from io import StringIO
import base64

# Configuração da página
st.set_page_config(
    page_title="Sistema de Estoque Completo",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS customizado
st.markdown("""
<style>
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 2rem;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 10px 30px rgba(0,0,0,0.2);
    }
    
    .config-box {
        background: #f0f8ff;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #4285f4;
        margin-bottom: 1rem;
    }
    
    .metric-card {
        background: white;
        padding: 1.5rem;
        border-radius: 10px;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        text-align: center;
        border-left: 4px solid #3498db;
    }
    
    .alert-success { background: #d4edda; color: #155724; padding: 1rem; border-radius: 8px; border-left: 4px solid #28a745; }
    .alert-warning { background: #fff3cd; color: #856404; padding: 1rem; border-radius: 8px; border-left: 4px solid #ffc107; }
    .alert-danger { background: #f8d7da; color: #721c24; padding: 1rem; border-radius: 8px; border-left: 4px solid #dc3545; }
    
    .report-section {
        background: #f8f9fa;
        padding: 2rem;
        border-radius: 10px;
        margin: 2rem 0;
        border: 1px solid #dee2e6;
    }
    
    .stButton > button {
        width: 100%;
        border-radius: 8px;
        border: none;
        padding: 0.75rem 1rem;
        font-weight: 600;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 5px 15px rgba(0,0,0,0.2);
    }
</style>
""", unsafe_allow_html=True)

# Funções auxiliares
@st.cache_data(ttl=60)
def carregar_planilha(url):
    """Carrega dados do Google Sheets"""
    if not url:
        return pd.DataFrame()
    
    try:
        # Converter URL para CSV
        if '/edit' in url:
            csv_url = url.replace('/edit#gid=0', '/export?format=csv').replace('/edit', '/export?format=csv')
        else:
            csv_url = url
        
        response = requests.get(csv_url, timeout=10)
        response.raise_for_status()
        
        df = pd.read_csv(StringIO(response.text))
        
        # Validar colunas
        required_cols = ['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max', 'custo_unitario']
        missing_cols = [col for col in required_cols if col not in df.columns]
        
        if missing_cols:
            st.error(f"❌ Colunas faltando: {missing_cols}")
            return pd.DataFrame()
        
        # Limpar e converter dados
        df = df.dropna(subset=['codigo', 'nome'])
        df['estoque_atual'] = pd.to_numeric(df['estoque_atual'], errors='coerce').fillna(0)
        df['estoque_min'] = pd.to_numeric(df['estoque_min'], errors='coerce').fillna(0)
        df['estoque_max'] = pd.to_numeric(df['estoque_max'], errors='coerce').fillna(0)
        df['custo_unitario'] = pd.to_numeric(df['custo_unitario'], errors='coerce').fillna(0)
        
        return df
        
    except Exception as e:
        st.error(f"❌ Erro ao carregar planilha: {str(e)}")
        return pd.DataFrame()

def adicionar_status(df):
    """Adiciona colunas de status e semáforo"""
    if df.empty:
        return df
    
    df['status'] = df.apply(lambda row: 
        'CRÍTICO' if row['estoque_atual'] <= row['estoque_min']
        else 'ATENÇÃO' if row['estoque_atual'] <= row['estoque_min'] * 1.5
        else 'OK', axis=1)
    
    df['semaforo'] = df['status'].map({
        'OK': '🟢',
        'ATENÇÃO': '🟡', 
        'CRÍTICO': '🔴'
    })
    
    return df

def gerar_csv_download(df, filename):
    """Gera link de download para CSV"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a href="data:file/csv;base64,{b64}" download="{filename}">📥 Baixar {filename}</a>'

# Header principal
st.markdown("""
<div class="main-header">
    <h1>📦 Sistema Completo de Controle de Estoque</h1>
    <p>Dashboard Profissional com Google Sheets + Relatórios + Semáforos</p>
    <small>Versão 2.0 - Desenvolvido para máxima eficiência</small>
</div>
""", unsafe_allow_html=True)

# Sidebar - Configuração
st.sidebar.title("⚙️ Configuração do Sistema")

# URL do Google Sheets (FIXO)
st.sidebar.markdown("### 🔗 Conexão Google Sheets")
sheets_url = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/edit?usp=sharing"

# Mostrar URL configurada
st.sidebar.success("✅ Planilha configurada automaticamente!")
st.sidebar.markdown(f"**Planilha:** template_estoque")
st.sidebar.markdown("🔗 [Abrir planilha](https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/edit?usp=sharing)")

if sheets_url != st.session_state.get('sheets_url', ''):
    st.session_state['sheets_url'] = sheets_url
    st.cache_data.clear()

# Controles
st.sidebar.markdown("### 🎛️ Controles")
col_ctrl1, col_ctrl2 = st.sidebar.columns(2)

with col_ctrl1:
    if st.button("🔄 Atualizar", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

with col_ctrl2:
    auto_refresh = st.checkbox("Auto 30s", value=False)

# Instruções na sidebar
with st.sidebar.expander("📋 Como Configurar", expanded=False):
    st.markdown("""
    **1. Criar Google Sheets:**
    - Colunas obrigatórias:
      - `codigo`
      - `nome` 
      - `categoria`
      - `estoque_atual`
      - `estoque_min`
      - `estoque_max`
      - `custo_unitario`
    
    **2. Compartilhar:**
    - File → Share → "Anyone with link can view"
    
    **3. Colar URL:**
    - Cole a URL completa aqui
    """)

# Template para download
with st.sidebar.expander("📄 Template da Planilha"):
    template_data = {
        'codigo': ['P001', 'P002', 'P003'],
        'nome': ['Produto A', 'Produto B', 'Produto C'],
        'categoria': ['Eletrônicos', 'Roupas', 'Casa'],
        'estoque_atual': [150, 30, 80],
        'estoque_min': [50, 40, 60],
        'estoque_max': [300, 200, 250],
        'custo_unitario': [25.50, 15.75, 32.00]
    }
    template_df = pd.DataFrame(template_data)
    
    csv_template = template_df.to_csv(index=False)
    st.download_button(
        label="📥 Baixar Template",
        data=csv_template,
        file_name="template_estoque.csv",
        mime="text/csv",
        use_container_width=True
    )

# Verificar se há URL configurada
if not sheets_url:
    st.markdown("""
    <div class="config-box">
        <h3>🚀 Primeiros Passos</h3>
        <ol>
            <li><strong>Baixe o template</strong> na barra lateral</li>
            <li><strong>Crie uma planilha</strong> no Google Sheets</li>
            <li><strong>Importe o template</strong> ou crie as colunas manualmente</li>
            <li><strong>Compartilhe</strong> como "Anyone with link can view"</li>
            <li><strong>Cole a URL</strong> na barra lateral</li>
        </ol>
    </div>
    """, unsafe_allow_html=True)
    
    st.subheader("📋 Exemplo de Estrutura da Planilha")
    st.dataframe(pd.DataFrame(template_data), use_container_width=True)
    st.stop()

# Carregar dados
with st.spinner("📊 Carregando dados da planilha..."):
    produtos_df = carregar_planilha(sheets_url)

if produtos_df.empty:
    st.error("❌ Não foi possível carregar dados. Verifique a URL e permissões da planilha.")
    st.stop()

# Adicionar status
produtos_df = adicionar_status(produtos_df)

# Status da conexão
st.markdown(f"""
<div class="config-box">
    ✅ <strong>Conectado com sucesso!</strong> | 
    📊 {len(produtos_df)} produtos carregados | 
    🕐 Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
</div>
""", unsafe_allow_html=True)

# Métricas principais
st.subheader("📊 Resumo Executivo")

col1, col2, col3, col4, col5 = st.columns(5)

total_produtos = len(produtos_df)
produtos_ok = len(produtos_df[produtos_df['status'] == 'OK'])
produtos_atencao = len(produtos_df[produtos_df['status'] == 'ATENÇÃO'])
produtos_criticos = len(produtos_df[produtos_df['status'] == 'CRÍTICO'])
valor_total = (produtos_df['estoque_atual'] * produtos_df['custo_unitario']).sum()

with col1:
    st.metric("📦 Total Produtos", total_produtos)

with col2:
    st.metric("🟢 OK", produtos_ok, delta=f"{produtos_ok/total_produtos*100:.1f}%")

with col3:
    st.metric("🟡 Atenção", produtos_atencao, delta=f"{produtos_atencao/total_produtos*100:.1f}%")

with col4:
    st.metric("🔴 Crítico", produtos_criticos, delta=f"{produtos_criticos/total_produtos*100:.1f}%")

with col5:
    st.metric("💰 Valor Total", f"R$ {valor_total:,.2f}")

# Layout principal
col_main, col_side = st.columns([2.5, 1])

with col_main:
    # Tabela principal com filtros
    st.subheader("🗂️ Controle de Estoque com Semáforos")
    
    # Filtros
    col_f1, col_f2, col_f3 = st.columns(3)
    
    with col_f1:
        categoria_filter = st.selectbox(
            "📂 Categoria:",
            ['Todas'] + sorted(produtos_df['categoria'].unique().tolist())
        )
    
    with col_f2:
        status_filter = st.selectbox(
            "🚦 Status:",
            ['Todos', 'CRÍTICO', 'ATENÇÃO', 'OK']
        )
    
    with col_f3:
        busca_produto = st.text_input("🔍 Buscar produto:", placeholder="Digite nome ou código")
    
    # Aplicar filtros
    df_filtrado = produtos_df.copy()
    
    if categoria_filter != 'Todas':
        df_filtrado = df_filtrado[df_filtrado['categoria'] == categoria_filter]
    
    if status_filter != 'Todos':
        df_filtrado = df_filtrado[df_filtrado['status'] == status_filter]
    
    if busca_produto:
        mask = (df_filtrado['nome'].str.contains(busca_produto, case=False, na=False) | 
                df_filtrado['codigo'].str.contains(busca_produto, case=False, na=False))
        df_filtrado = df_filtrado[mask]
    
    # Exibir tabela
    if len(df_filtrado) > 0:
        st.dataframe(
            df_filtrado[['semaforo', 'codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max', 'status']],
            use_container_width=True,
            height=400
        )
        st.caption(f"Mostrando {len(df_filtrado)} de {len(produtos_df)} produtos")
    else:
        st.info("🔍 Nenhum produto encontrado com os filtros aplicados")

with col_side:
    # Gráfico de distribuição
    st.subheader("📈 Distribuição por Status")
    
    status_counts = produtos_df['status'].value_counts()
    
    fig_pie = px.pie(
        values=status_counts.values,
        names=status_counts.index,
        color=status_counts.index,
        color_discrete_map={
            'OK': '#28a745',
            'ATENÇÃO': '#ffc107',
            'CRÍTICO': '#dc3545'
        }
    )
    fig_pie.update_traces(textposition='inside', textinfo='percent+label')
    fig_pie.update_layout(height=300, showlegend=False)
    st.plotly_chart(fig_pie, use_container_width=True)
    
    # Alertas críticos
    st.subheader("🚨 Alertas Críticos")
    produtos_criticos_lista = produtos_df[produtos_df['status'] == 'CRÍTICO']
    
    if len(produtos_criticos_lista) > 0:
        for _, produto in produtos_criticos_lista.iterrows():
            faltante = produto['estoque_min'] - produto['estoque_atual']
            st.markdown(f"""
            <div class="alert-danger">
                <strong>{produto['nome']}</strong><br>
                Estoque: {produto['estoque_atual']} | Mín: {produto['estoque_min']}<br>
                <strong>Faltam: {faltante} unidades</strong>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-success">✅ Nenhum produto crítico!</div>', unsafe_allow_html=True)

# Análise por categoria
st.subheader("📊 Análise por Categoria")

col_cat1, col_cat2 = st.columns([2, 1])

with col_cat1:
    categoria_stats = produtos_df.groupby('categoria').agg({
        'estoque_atual': 'sum',
        'codigo': 'count',
        'custo_unitario': 'mean'
    }).reset_index()
    categoria_stats.columns = ['Categoria', 'Estoque Total', 'Qtd Produtos', 'Custo Médio']
    categoria_stats['Valor Total'] = categoria_stats['Estoque Total'] * categoria_stats['Custo Médio']
    
    fig_bar = px.bar(
        categoria_stats,
        x='Categoria',
        y='Estoque Total',
        title="Estoque Total por Categoria",
        color='Valor Total',
        color_continuous_scale='viridis',
        text='Estoque Total'
    )
    fig_bar.update_traces(texttemplate='%{text}', textposition='outside')
    fig_bar.update_layout(height=400)
    st.plotly_chart(fig_bar, use_container_width=True)

with col_cat2:
    st.markdown("**📋 Resumo por Categoria**")
    for _, row in categoria_stats.iterrows():
        st.metric(
            f"📦 {row['Categoria']}", 
            f"{row['Estoque Total']:.0f}",
            delta=f"{row['Qtd Produtos']} produtos"
        )

# Seção de Relatórios
st.markdown("""
<div class="report-section">
    <h2>🖨️ Central de Relatórios</h2>
    <p>Gere relatórios detalhados para impressão e análise</p>
</div>
""", unsafe_allow_html=True)

col_rel1, col_rel2, col_rel3 = st.columns(3)

with col_rel1:
    if st.button("📋 Relatório - Produtos Críticos", type="primary", use_container_width=True):
        produtos_criticos = produtos_df[produtos_df['status'] == 'CRÍTICO'].copy()
        
        if len(produtos_criticos) > 0:
            produtos_criticos['qtd_faltante'] = produtos_criticos['estoque_min'] - produtos_criticos['estoque_atual']
            produtos_criticos['valor_reposicao'] = produtos_criticos['qtd_faltante'] * produtos_criticos['custo_unitario']
            
            relatorio = produtos_criticos[['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'qtd_faltante', 'custo_unitario', 'valor_reposicao']].copy()
            relatorio.columns = ['Código', 'Produto', 'Categoria', 'Estoque Atual', 'Estoque Mín', 'Qtd Faltante', 'Custo Unit', 'Valor Reposição']
            
            st.markdown("### 🔴 RELATÓRIO - PRODUTOS CRÍTICOS")
            st.markdown(f"**📅 Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
            st.markdown(f"**📊 Total de produtos críticos:** {len(produtos_criticos)}")
            st.markdown(f"**💰 Valor total para reposição:** R$ {relatorio['Valor Reposição'].sum():,.2f}")
            
            st.dataframe(relatorio, use_container_width=True)
            
            csv_data = relatorio.to_csv(index=False)
            st.download_button(
                label="💾 Baixar Relatório (CSV)",
                data=csv_data,
                file_name=f"produtos_criticos_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
                use_container_width=True
            )
        else:
            st.success("✅ Nenhum produto em situação crítica!")

with col_rel2:
    if st.button("📊 Relatório Geral", type="primary", use_container_width=True):
        relatorio_geral = produtos_df.copy()
        relatorio_geral['valor_estoque'] = relatorio_geral['estoque_atual'] * relatorio_geral['custo_unitario']
        relatorio_geral['percentual_ocupacao'] = (relatorio_geral['estoque_atual'] / relatorio_geral['estoque_max'] * 100).round(1)
        
        relatorio_final = relatorio_geral[['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max', 'custo_unitario', 'valor_estoque', 'percentual_ocupacao', 'status']].copy()
        relatorio_final.columns = ['Código', 'Produto', 'Categoria', 'Estoque Atual', 'Estoque Mín', 'Estoque Máx', 'Custo Unit', 'Valor Estoque', '% Ocupação', 'Status']
        
        st.markdown("### 📊 RELATÓRIO GERAL DE ESTOQUE")
        st.markdown(f"**📅 Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        
        col_res1, col_res2, col_res3, col_res4 = st.columns(4)
        with col_res1:
            st.metric("Total Produtos", len(produtos_df))
        with col_res2:
            st.metric("Valor Total", f"R$ {relatorio_final['Valor Estoque'].sum():,.2f}")
        with col_res3:
            st.metric("Unidades Total", f"{relatorio_final['Estoque Atual'].sum():,.0f}")
        with col_res4:
            ocupacao_media = relatorio_final['% Ocupação'].mean()
            st.metric("Ocupação Média", f"{ocupacao_media:.1f}%")
        
        st.dataframe(relatorio_final, use_container_width=True)
        
        csv_data = relatorio_final.to_csv(index=False)
        st.download_button(
            label="💾 Baixar Relatório (CSV)",
            data=csv_data,
            file_name=f"relatorio_geral_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )

with col_rel3:
    if st.button("📈 Relatório por Categoria", type="primary", use_container_width=True):
        relatorio_categoria = produtos_df.groupby('categoria').agg({
            'codigo': 'count',
            'estoque_atual': ['sum', 'mean'],
            'custo_unitario': 'mean'
        }).round(2)
        
        relatorio_categoria.columns = ['Qtd Produtos', 'Estoque Total', 'Estoque Médio', 'Custo Médio']
        relatorio_categoria['Valor Total'] = (produtos_df.groupby('categoria').apply(lambda x: (x['estoque_atual'] * x['custo_unitario']).sum())).round(2)
        relatorio_categoria = relatorio_categoria.reset_index()
        
        st.markdown("### 📈 RELATÓRIO POR CATEGORIA")
        st.markdown(f"**📅 Data:** {datetime.now().strftime('%d/%m/%Y %H:%M')}")
        
        st.dataframe(relatorio_categoria, use_container_width=True)
        
        csv_data = relatorio_categoria.to_csv(index=False)
        st.download_button(
            label="💾 Baixar Relatório (CSV)",
            data=csv_data,
            file_name=f"relatorio_categoria_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=True
        )

# Auto-refresh
if auto_refresh:
    time.sleep(30)
    st.rerun()

# Footer
st.markdown("---")
st.markdown("""
<div style='text-align: center; color: #666; padding: 2rem;'>
    <h4>📦 Sistema Completo de Controle de Estoque</h4>
    <p>Integração Google Sheets • Relatórios Profissionais • Semáforos Visuais</p>
    <p><strong>Versão 2.0</strong> | Desenvolvido para máxima eficiência e praticidade</p>
    <small>Última atualização: {}</small>
</div>
""".format(datetime.now().strftime("%d/%m/%Y %H:%M:%S")), unsafe_allow_html=True)
