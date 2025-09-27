import streamlit as st
import pandas as pd
import requests
import json
from datetime import datetime
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from io import StringIO

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
    ["Visão Geral", "Análise Mín/Máx", "Movimentação"]
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
            'semaforo', 'codigo', 'nome', 'categoria', 
            'estoque_atual', 'estoque_min', 'estoque_max', coluna_analise
        ]].copy()
        
        # Converter para inteiros (remover .0)
        tabela_exibicao['estoque_atual'] = tabela_exibicao['estoque_atual'].astype(int)
        tabela_exibicao['estoque_min'] = tabela_exibicao['estoque_min'].astype(int)
        tabela_exibicao['estoque_max'] = tabela_exibicao['estoque_max'].astype(int)
        tabela_exibicao[coluna_analise] = tabela_exibicao[coluna_analise].astype(int)
        
        tabela_exibicao.columns = [
            '🚦', 'Código', 'Produto', 'Categoria', 
            'Atual', 'Mínimo', 'Máximo', titulo_coluna
        ]
        
        # Ordenar por valor da análise (decrescente)
        tabela_exibicao = tabela_exibicao.sort_values(titulo_coluna, ascending=False)
        
        st.dataframe(
            tabela_exibicao,
            use_container_width=True,
            height=400
        )
        
        # Botão para download CSV
        csv_data = tabela_exibicao.to_csv(index=False)
        st.download_button(
            label=f"📥 Download {analise_tipo} - CSV",
            data=csv_data,
            file_name=f"analise_{analise_tipo.lower().replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv"
        )
        
        # Gráfico
        if len(df_analise) <= 20:  # Só mostrar gráfico se não for muitos produtos
            fig = px.bar(
                df_analise.head(20),
                x='codigo',
                y=coluna_analise,
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
