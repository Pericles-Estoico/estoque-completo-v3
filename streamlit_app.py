import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from io import StringIO

# Configuração
st.set_page_config(
    page_title="📦 Sistema de Estoque - Desktop",
    page_icon="📦",
    layout="wide"
)

# CSS
st.markdown("""
<style>
.main .block-container { padding: 2rem; }
.metric-card { 
    background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
    padding: 1.5rem; 
    border-radius: 10px; 
    color: white;
    text-align: center;
    margin: 1rem 0;
}
.alert-success { 
    background: #d4edda; 
    color: #155724; 
    padding: 1rem; 
    border-radius: 8px; 
    margin: 1rem 0;
    border-left: 4px solid #28a745;
}
.alert-error { 
    background: #f8d7da; 
    color: #721c24; 
    padding: 1rem; 
    border-radius: 8px; 
    margin: 1rem 0;
    border-left: 4px solid #dc3545;
}
.report-section {
    background: #f8f9fa;
    padding: 1.5rem;
    border-radius: 10px;
    margin: 1rem 0;
    border: 1px solid #dee2e6;
}
</style>
""", unsafe_allow_html=True)

# URLs
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzCxotWn-SXG52CXU7tNnd7KtBhx1uYwHr-ka2qWjswTcfj3QvHuA1VvDo-BL_fpg8U/exec"

# Funções
@st.cache_data(ttl=30)
def carregar_produtos():
    try:
        response = requests.get(SHEETS_URL, timeout=10)
        df = pd.read_csv(StringIO(response.text))
        
        # Validar colunas
        required_cols = ['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max']
        for col in required_cols:
            if col not in df.columns:
                st.error(f"Coluna '{col}' não encontrada na planilha")
                return pd.DataFrame()
        
        # Limpar dados
        df = df.dropna(subset=['codigo', 'nome'])
        df['estoque_atual'] = pd.to_numeric(df['estoque_atual'], errors='coerce').fillna(0)
        df['estoque_min'] = pd.to_numeric(df['estoque_min'], errors='coerce').fillna(0)
        df['estoque_max'] = pd.to_numeric(df['estoque_max'], errors='coerce').fillna(0)
        
        # Calcular faltas
        df['falta_min'] = (df['estoque_min'] - df['estoque_atual']).clip(lower=0)
        df['falta_max'] = (df['estoque_max'] - df['estoque_atual']).clip(lower=0)
        
        # Calcular status
        df['status'] = df.apply(lambda row: 
            'CRÍTICO' if row['estoque_atual'] <= row['estoque_min'] 
            else 'BAIXO' if row['estoque_atual'] <= row['estoque_min'] * 1.2
            else 'OK', axis=1)
        
        return df
        
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {str(e)}")
        return pd.DataFrame()

def movimentar_estoque(codigo, quantidade, tipo):
    try:
        data = {
            'codigo': str(codigo),
            'quantidade': int(quantidade),
            'tipo': tipo
        }
        
        response = requests.post(WEBHOOK_URL, json=data, timeout=15)
        result = response.json()
        
        if result.get('success'):
            return {
                'success': True,
                'message': f'{tipo.title()} realizada com sucesso!',
                'novo_estoque': result.get('novoEstoque', 0)
            }
        else:
            return {
                'success': False,
                'error': result.get('error', 'Erro desconhecido')
            }
        
    except Exception as e:
        return {'success': False, 'error': str(e)}

# Interface Principal
st.title("📦 Sistema Completo de Controle de Estoque")
st.markdown("**Versão Desktop** - Dashboard Profissional com Relatórios Completos")

# Carregar dados
produtos_df = carregar_produtos()

if produtos_df.empty:
    st.error("❌ Não foi possível carregar os produtos da planilha")
    st.stop()

# Métricas principais
col1, col2, col3, col4 = st.columns(4)

total_produtos = len(produtos_df)
estoque_total = produtos_df['estoque_atual'].sum()
produtos_criticos = len(produtos_df[produtos_df['status'] == 'CRÍTICO'])
produtos_baixos = len(produtos_df[produtos_df['status'] == 'BAIXO'])

with col1:
    st.markdown(f"""
    <div class="metric-card">
        <h3>📦 Total Produtos</h3>
        <h2>{total_produtos}</h2>
    </div>
    """, unsafe_allow_html=True)

with col2:
    st.markdown(f"""
    <div class="metric-card">
        <h3>📊 Estoque Total</h3>
        <h2>{estoque_total:,.0f}</h2>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div class="metric-card">
        <h3>🚨 Críticos</h3>
        <h2>{produtos_criticos}</h2>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div class="metric-card">
        <h3>⚠️ Baixos</h3>
        <h2>{produtos_baixos}</h2>
    </div>
    """, unsafe_allow_html=True)

# Seção de Movimentação
st.markdown("---")
st.subheader("🔄 Movimentação de Estoque")

col1, col2 = st.columns([2, 1])

with col1:
    # Filtros
    categorias = ['Todas'] + sorted(produtos_df['categoria'].unique().tolist())
    categoria_selecionada = st.selectbox("📂 Filtrar por categoria:", categorias)
    
    if categoria_selecionada == 'Todas':
        produtos_filtrados = produtos_df
    else:
        produtos_filtrados = produtos_df[produtos_df['categoria'] == categoria_selecionada]
    
    # Busca
    busca = st.text_input("🔍 Buscar produto:", placeholder="Digite código ou nome do produto...")
    
    if busca and len(busca) >= 2:
        mask = (produtos_filtrados['codigo'].astype(str).str.contains(busca, case=False, na=False) | 
                produtos_filtrados['nome'].astype(str).str.contains(busca, case=False, na=False))
        produtos_encontrados = produtos_filtrados[mask]
        
        if not produtos_encontrados.empty:
            produto_selecionado = st.selectbox(
                "Produto encontrado:",
                produtos_encontrados.index,
                format_func=lambda x: f"{produtos_encontrados.loc[x, 'codigo']} - {produtos_encontrados.loc[x, 'nome']}"
            )
            
            produto = produtos_encontrados.loc[produto_selecionado]
            
            st.info(f"**Estoque atual:** {produto['estoque_atual']} unidades")
            
            col_mov1, col_mov2 = st.columns(2)
            
            with col_mov1:
                qtd_entrada = st.number_input("Quantidade para entrada:", min_value=1, value=1, key="entrada_desk")
                if st.button("➕ Registrar Entrada", key="btn_entrada_desk"):
                    resultado = movimentar_estoque(produto['codigo'], qtd_entrada, 'entrada')
                    if resultado['success']:
                        st.markdown(f'<div class="alert-success">✅ {resultado["message"]}</div>', unsafe_allow_html=True)
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.markdown(f'<div class="alert-error">❌ {resultado["error"]}</div>', unsafe_allow_html=True)
            
            with col_mov2:
                qtd_saida = st.number_input("Quantidade para saída:", min_value=1, max_value=max(1, int(produto['estoque_atual'])), value=1, key="saida_desk")
                if st.button("➖ Registrar Saída", key="btn_saida_desk"):
                    resultado = movimentar_estoque(produto['codigo'], qtd_saida, 'saida')
                    if resultado['success']:
                        st.markdown(f'<div class="alert-success">✅ {resultado["message"]}</div>', unsafe_allow_html=True)
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.markdown(f'<div class="alert-error">❌ {resultado["error"]}</div>', unsafe_allow_html=True)

with col2:
    st.markdown("### 📊 Status Rápido")
    status_counts = produtos_df['status'].value_counts()
    for status, count in status_counts.items():
        cor = "🟢" if status == "OK" else "🟡" if status == "BAIXO" else "🔴"
        st.write(f"{cor} **{status}**: {count} produtos")

# Seção de Relatórios
st.markdown("---")
st.subheader("📊 Relatórios e Análises")

tab1, tab2, tab3, tab4 = st.tabs(["📋 Estoque Crítico", "📈 Reabastecimento", "📊 Relatório Geral", "📄 Planilha Completa"])

with tab1:
    st.markdown('<div class="report-section">', unsafe_allow_html=True)
    st.markdown("### 🚨 Produtos com Estoque Crítico")
    
    criticos = produtos_df[produtos_df['status'] == 'CRÍTICO']
    if not criticos.empty:
        relatorio_critico = criticos[['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'falta_min']].copy()
        relatorio_critico.columns = ['Código', 'Produto', 'Categoria', 'Estoque Atual', 'Estoque Mín', 'Qtd Faltante']
        
        st.dataframe(relatorio_critico, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            csv_critico = relatorio_critico.to_csv(index=False)
            st.download_button("💾 Baixar CSV", csv_critico, "produtos_criticos.csv", "text/csv")
        with col2:
            st.markdown("🖨️ **Para imprimir:** Use Ctrl+P no navegador")
    else:
        st.success("✅ Nenhum produto com estoque crítico!")
    
    st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.markdown('<div class="report-section">', unsafe_allow_html=True)
    st.markdown("### 📈 Oportunidades de Reabastecimento")
    
    reabastecimento = produtos_df[produtos_df['falta_max'] > 0]
    if not reabastecimento.empty:
        relatorio_reab = reabastecimento[['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_max', 'falta_max']].copy()
        relatorio_reab.columns = ['Código', 'Produto', 'Categoria', 'Estoque Atual', 'Estoque Máx', 'Pode Comprar']
        
        st.dataframe(relatorio_reab, use_container_width=True)
        
        col1, col2 = st.columns(2)
        with col1:
            csv_reab = relatorio_reab.to_csv(index=False)
            st.download_button("💾 Baixar CSV", csv_reab, "reabastecimento.csv", "text/csv")
        with col2:
            st.markdown("🖨️ **Para imprimir:** Use Ctrl+P no navegador")
    else:
        st.info("ℹ️ Todos os produtos estão no estoque máximo!")
    
    st.markdown('</div>', unsafe_allow_html=True)

with tab3:
    st.markdown('<div class="report-section">', unsafe_allow_html=True)
    st.markdown("### 📊 Relatório Executivo Completo")
    
    relatorio_geral = produtos_df[['codigo', 'nome', 'categoria', 'estoque_atual', 'estoque_min', 'estoque_max', 'falta_min', 'falta_max', 'status']].copy()
    relatorio_geral.columns = ['Código', 'Produto', 'Categoria', 'Atual', 'Mín', 'Máx', 'Falta Mín', 'Falta Máx', 'Status']
    
    st.dataframe(relatorio_geral, use_container_width=True)
    
    # Resumo executivo
    st.markdown("#### 📈 Resumo Executivo")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de Produtos", total_produtos)
    with col2:
        st.metric("Unidades em Estoque", f"{estoque_total:,.0f}")
    with col3:
        st.metric("Produtos Críticos", produtos_criticos)
    
    col1, col2 = st.columns(2)
    with col1:
        csv_geral = relatorio_geral.to_csv(index=False)
        st.download_button("💾 Baixar Relatório CSV", csv_geral, "relatorio_completo.csv", "text/csv")
    with col2:
        st.markdown("🖨️ **Para imprimir:** Use Ctrl+P no navegador")
    
    st.markdown('</div>', unsafe_allow_html=True)

with tab4:
    st.markdown('<div class="report-section">', unsafe_allow_html=True)
    st.markdown("### 📄 Planilha Completa para Download")
    
    st.markdown("**Dados completos da planilha com todas as colunas calculadas:**")
    
    planilha_completa = produtos_df.copy()
    st.dataframe(planilha_completa, use_container_width=True)
    
    col1, col2, col3 = st.columns(3)
    with col1:
        csv_completo = planilha_completa.to_csv(index=False)
        st.download_button("💾 Baixar Planilha CSV", csv_completo, f"estoque_completo_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", "text/csv")
    with col2:
        st.markdown("🖨️ **Para imprimir:** Use Ctrl+P no navegador")
    with col3:
        if st.button("🔄 Atualizar Dados"):
            st.cache_data.clear()
            st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

# Rodapé
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.caption(f"📦 Sistema Desktop • Última atualização: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
with col2:
    st.caption("🔗 Conectado ao Google Sheets")
with col3:
    st.caption("📱 Versão Mobile disponível")
