import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from io import StringIO
import math
import unicodedata
import plotly.express as px

# ======================================================
# Config da página
# ======================================================
st.set_page_config(
    page_title="Estoque Cockpit - Silva Holding",
    page_icon="📦",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ======================================================
# URLs (troque se precisar)
# ======================================================
SHEETS_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/export?format=csv"
WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbxTX9uUWnByw6sk6MtuJ5FbjV7zeBKYEoUPPlUlUDS738QqocfCd_NAlh9Eh25XhQywTw/exec"

# ======================================================
# Helpers
# ======================================================
def safe_int(x, default=0):
    try:
        if x is None:
            return default
        if isinstance(x, float) and math.isnan(x):
            return default
        s = str(x).strip()
        if s.lower() in {"", "nan", "none", "null", "n/a"}:
            return default
        return int(float(s.replace(",", ".")))
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
        try:
            out.append(int(float(p.replace(",", "."))))
        except Exception:
            pass
    return out

def normaliza_codigo(s):
    return str(s).strip().upper()

def normaliza_coluna(nome):
    nome = unicodedata.normalize('NFKD', str(nome)).encode('ASCII', 'ignore').decode('ASCII')
    return nome.lower().strip()

# ======================================================
# CSS
# ======================================================
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
.info-box{background:#e7f1ff;border-left:4px solid #2f6bff;padding:1rem;border-radius:5px;margin:1rem 0}
</style>
""", unsafe_allow_html=True)

# ======================================================
# Semáforo
# ======================================================
def calcular_semaforo(estoque_atual, estoque_min, estoque_max):
    try:
        a = float(estoque_atual)
        mn = float(estoque_min)
        mx = float(estoque_max)
    except Exception:
        a = mn = mx = 0.0
    if a < mn:
        return "CRÍTICO", "#ff4444"
    elif a <= mn * 1.2:
        return "BAIXO", "#ffaa00"
    elif a > mx:
        return "EXCESSO", "#0088ff"
    else:
        return "OK", "#00aa00"

# ======================================================
# Carregar produtos do Sheets
# ======================================================
@st.cache_data(ttl=30)
def carregar_produtos():
    try:
        resp = requests.get(SHEETS_URL, timeout=15)
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        # colunas mínimas
        for c in ['codigo','nome','categoria','estoque_atual','estoque_min','estoque_max','componentes','quantidades','eh_kit']:
            if c not in df.columns:
                df[c] = '' if c in ['componentes','quantidades','eh_kit'] else 0
        df['estoque_atual'] = pd.to_numeric(df['estoque_atual'], errors='coerce').fillna(0).astype(int)
        df['estoque_min']   = pd.to_numeric(df['estoque_min'], errors='coerce').fillna(0).astype(int)
        df['estoque_max']   = pd.to_numeric(df['estoque_max'], errors='coerce').fillna(0).astype(int)
        df['codigo']        = df['codigo'].astype(str)
        df['codigo_norm']   = df['codigo'].apply(normaliza_codigo)
        df['eh_kit']        = df['eh_kit'].astype(str).str.strip().str.lower()
        return df
    except Exception as e:
        st.error(f"Erro ao carregar planilha: {e}")
        return pd.DataFrame(columns=['codigo','codigo_norm','nome','categoria','estoque_atual','estoque_min','estoque_max','eh_kit','componentes','quantidades'])

produtos_df = carregar_produtos()
if produtos_df.empty:
    st.error("Não foi possível carregar os dados da planilha.")
    st.stop()

# Derivados / status
status_list = []
cor_list = []
for _, r in produtos_df.iterrows():
    stt, cor = calcular_semaforo(r['estoque_atual'], r['estoque_min'], r['estoque_max'])
    status_list.append(stt)
    cor_list.append(cor)
produtos_df['status'] = status_list
produtos_df['cor'] = cor_list
produtos_df['falta_para_min'] = (produtos_df['estoque_min'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['falta_para_max'] = (produtos_df['estoque_max'] - produtos_df['estoque_atual']).clip(lower=0)
produtos_df['excesso_sobre_max'] = (produtos_df['estoque_atual'] - produtos_df['estoque_max']).clip(lower=0)
produtos_df['diferenca_min_max'] = produtos_df['estoque_max'] - produtos_df['estoque_min']

# ======================================================
# Sidebar (filtros e modo teste)
# ======================================================
st.sidebar.header("🕹️ CONTROLES DE VOO")
MODO_TESTE = st.sidebar.checkbox("✏️ Modo Teste (simulação, não altera planilha)", value=True)
st.sidebar.caption("Todas as operações serão simuladas (nenhum dado será enviado ao Google Apps Script).")

categorias = ['Todas'] + sorted(produtos_df['categoria'].dropna().astype(str).unique().tolist())
categoria_filtro = st.sidebar.selectbox("📂 Categoria:", categorias)

status_opcoes = ['Todos', 'CRÍTICO', 'BAIXO', 'OK', 'EXCESSO']
status_filtro = st.sidebar.selectbox("🚦 Status:", status_opcoes)

tipo_analise = st.sidebar.radio(
    "Tipo de Análise:",
    ["Visão Geral", "Análise Mín/Máx", "Movimentação", "Baixa por Faturamento", "Histórico de Baixas", "Relatório de Faltantes"]
)

df_filtrado = produtos_df.copy()
if categoria_filtro != 'Todas':
    df_filtrado = df_filtrado[df_filtrado['categoria'] == categoria_filtro]
if status_filtro != 'Todos':
    df_filtrado = df_filtrado[df_filtrado['status'] == status_filtro]

# ======================================================
# Webhook (movimentar) — respeita MODO_TESTE
# ======================================================
def movimentar_estoque(codigo, quantidade, tipo, colaborador):
    if MODO_TESTE:
        # simula sucesso
        return {'success': True, 'novo_estoque': 'SIMULAÇÃO', 'message': 'Simulado (modo teste)'}
    try:
        payload = {'codigo': codigo, 'quantidade': safe_int(quantidade,0), 'tipo': tipo, 'colaborador': colaborador}
        r = requests.post(WEBHOOK_URL, json=payload, timeout=20)
        return r.json()
    except Exception as e:
        return {'success': False, 'message': f'Erro: {e}'}

# ======================================================
# Expansão de kits
# ======================================================
def expandir_kits(df_fatura, produtos_df):
    # monta dict de kits
    kits = {}
    for _, r in produtos_df.iterrows():
        if str(r.get('eh_kit','')).strip().lower() == 'sim':
            comp = [c.strip().upper() for c in str(r.get('componentes','')).split(',') if c and c.strip()]
            qts  = parse_int_list(r.get('quantidades',''))
            if comp and qts and len(comp)==len(qts):
                kits[r['codigo_norm']] = list(zip(comp, qts))

    if not kits:
        # garante colunas padrão
        out = df_fatura[['codigo','quantidade']].copy()
        out['codigo'] = out['codigo'].astype(str)
        return out

    linhas = []
    for _, row in df_fatura.iterrows():
        c = normaliza_codigo(row['codigo'])
        q = safe_int(row['quantidade'], 0)
        if c in kits:
            for (c_comp, q_comp) in kits[c]:
                linhas.append({'codigo': c_comp, 'quantidade': q * safe_int(q_comp,0)})
        else:
            linhas.append({'codigo': c, 'quantidade': q})
    out = pd.DataFrame(linhas)
    out = out.groupby('codigo', as_index=False)['quantidade'].sum()
    return out

# ======================================================
# Processar faturamento (CORRIGIDO)
# ======================================================
def processar_faturamento(arquivo_upload, produtos_df):
    try:
        nome = arquivo_upload.name.lower()
        # carregar
        if nome.endswith('.csv'):
            df = None
            for enc in ['utf-8','utf-8-sig','latin1','iso-8859-1','cp1252','windows-1252']:
                try:
                    arquivo_upload.seek(0)
                    df = pd.read_csv(arquivo_upload, encoding=enc)
                    if df is not None and len(df.columns)>0:
                        break
                except Exception:
                    continue
            if df is None:
                return None, None, "Não foi possível ler o CSV. Tente salvar como UTF-8."
        elif nome.endswith('.xlsx'):
            df = pd.read_excel(arquivo_upload, engine='openpyxl')
        elif nome.endswith('.xls'):
            df = pd.read_excel(arquivo_upload, engine='xlrd')
        else:
            return None, None, "Formato não suportado. Use CSV/XLS/XLSX."

        # normaliza colunas
        df.rename(columns={c: normaliza_coluna(c) for c in df.columns}, inplace=True)
        if 'codigo' not in df.columns or 'quantidade' not in df.columns:
            return None, None, f"Arquivo deve conter colunas 'codigo' e 'quantidade'. Colunas encontradas: {list(df.columns)}"

        df['codigo_norm'] = df['codigo'].apply(normaliza_codigo)
        df['quantidade'] = df['quantidade'].apply(lambda x: safe_int(x,0)).astype(int)
        df = df[(df['codigo_norm']!='') & (df['quantidade']>0)]
        df = df.groupby('codigo_norm', as_index=False)['quantidade'].sum()

        # prepara para expandir kits (usa coluna 'codigo')
        df['codigo'] = df['codigo_norm']
        df = expandir_kits(df[['codigo','quantidade']], produtos_df)

        # encontrados x não encontrados
        estoque_codes = set(produtos_df['codigo_norm'])
        df['codigo_norm'] = df['codigo'].apply(normaliza_codigo)
        df['encontrado'] = df['codigo_norm'].isin(estoque_codes)

        encon = df[df['encontrado']].copy().reset_index(drop=True)
        nao   = df[~df['encontrado']].copy().reset_index(drop=True)

        if not encon.empty:
            base = produtos_df[['codigo_norm','nome','estoque_atual']].dropna(subset=['codigo_norm'])
            base = base.drop_duplicates(subset=['codigo_norm'], keep='last')
            # evita erro "index must be unique"
            map_idx = base.set_index('codigo_norm')[['nome','estoque_atual']].to_dict(orient='index')

            encon['nome'] = encon['codigo_norm'].map(lambda x: map_idx.get(x, {}).get('nome', 'N/A'))
            encon['estoque_atual'] = encon['codigo_norm'].map(lambda x: map_idx.get(x, {}).get('estoque_atual', 0))
            encon['estoque_atual'] = pd.to_numeric(encon['estoque_atual'], errors='coerce').fillna(0).astype(int)
            encon['quantidade'] = pd.to_numeric(encon['quantidade'], errors='coerce').fillna(0).astype(int)
            encon['estoque_final'] = encon['estoque_atual'] - encon['quantidade']

        return encon, nao, None

    except Exception as e:
        return None, None, f"Erro ao processar: {e}"

# ======================================================
# Header
# ======================================================
st.markdown("""
<div class="cockpit-header">
  <h1>COCKPIT DE CONTROLE — SILVA HOLDING</h1>
  <p>Visão, disciplina e execução: a tríade do estoque afiado.</p>
</div>
""", unsafe_allow_html=True)

# ======================================================
# Telas
# ======================================================
if tipo_analise == "Visão Geral":
    c1,c2,c3,c4,c5 = st.columns(5)
    with c1:
        st.markdown(f'<div class="metric-card"><h3>PRODUTOS</h3><h2>{len(df_filtrado)}</h2></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="metric-card"><h3>ESTOQUE TOTAL</h3><h2>{int(df_filtrado["estoque_atual"].sum()):,}</h2></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="metric-card"><h3>CRÍTICOS</h3><h2>{len(df_filtrado[df_filtrado["status"]=="CRÍTICO"])}</h2></div>', unsafe_allow_html=True)
    with c4:
        st.markdown(f'<div class="metric-card"><h3>BAIXOS</h3><h2>{len(df_filtrado[df_filtrado["status"]=="BAIXO"])}</h2></div>', unsafe_allow_html=True)
    with c5:
        st.markdown(f'<div class="metric-card"><h3>OK</h3><h2>{len(df_filtrado[df_filtrado["status"]=="OK"])}</h2></div>', unsafe_allow_html=True)

    col1,col2 = st.columns(2)
    with col1:
        st.subheader("Distribuição por Status")
        s = df_filtrado['status'].value_counts()
        if not s.empty:
            fig = px.pie(values=s.values, names=s.index,
                         color=s.index,
                         color_discrete_map={'CRÍTICO':'#ff4444','BAIXO':'#ffaa00','OK':'#00aa00','EXCESSO':'#0088ff'})
            fig.update_layout(height=320)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Sem dados para o filtro.")
    with col2:
        st.subheader("Estoque por Categoria")
        agg = df_filtrado.groupby('categoria')['estoque_atual'].sum().sort_values(ascending=False)
        if not agg.empty:
            fig2 = px.bar(x=agg.index, y=agg.values, color=agg.values, color_continuous_scale='viridis')
            fig2.update_layout(height=320, showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("Sem dados para o filtro.")

    st.subheader("🚨 Produtos em situação crítica")
    crit = df_filtrado[df_filtrado['status'].isin(['CRÍTICO','BAIXO'])].sort_values('estoque_atual')
    if crit.empty:
        st.success("Nenhum produto crítico/baixo 👍")
    else:
        for _, p in crit.head(12).iterrows():
            klass = p['status'].lower()
            st.markdown(
                f'<div class="status-card {klass}"><strong>{p["codigo"]}</strong> — {p["nome"]}<br>'
                f'<small>Atual: {int(p["estoque_atual"])} | Mín: {int(p["estoque_min"])} | Falta p/ mín: {int(p["falta_para_min"])}</small></div>',
                unsafe_allow_html=True
            )

elif tipo_analise == "Análise Mín/Máx":
    st.subheader("Análise Estoque Mínimo/Máximo")
    opt = st.selectbox("Tipo:", ["Falta para Mínimo","Falta para Máximo","Excesso sobre Máximo","Diferença Mín-Máx"])
    only_pos = st.checkbox("Mostrar apenas > 0", value=True)

    d = df_filtrado.copy()
    if opt == "Falta para Mínimo":
        col = 'falta_para_min'; title='Falta p/ Mín'
        if only_pos: d = d[d[col]>0]
    elif opt == "Falta para Máximo":
        col='falta_para_max'; title='Falta p/ Máx'
        if only_pos: d = d[d[col]>0]
    elif opt == "Excesso sobre Máximo":
        col='excesso_sobre_max'; title='Excesso s/ Máx'
        if only_pos: d = d[d[col]>0]
    else:
        col='diferenca_min_max'; title='Diferença Mín-Máx'
        if only_pos: d = d[d[col]>0]

    if d.empty:
        st.info("Nada a exibir com os filtros atuais.")
    else:
        show = d[['codigo','nome','categoria','estoque_atual','estoque_min','estoque_max',col,'status']].copy()
        show.columns = ['Código','Produto','Categoria','Atual','Mín','Máx',title,'Status']
        for c in ['Atual','Mín','Máx',title]:
            show[c] = pd.to_numeric(show[c], errors='coerce').fillna(0).astype(int)
        show = show.sort_values(title, ascending=False)
        st.dataframe(show, use_container_width=True, height=420)
        st.download_button(
            "📥 Baixar CSV",
            data=show.to_csv(index=False, encoding='utf-8-sig'),
            file_name=f"analise_{opt.replace(' ','_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )

elif tipo_analise == "Movimentação":
    st.subheader("Movimentação de Estoque")
    colaboradores = ['Pericles','Maria','Camila','Cris VantiStella']
    colab = st.selectbox("Colaborador:", colaboradores)
    busca = st.text_input("Buscar (código ou nome):", "")
    if busca and len(busca)>=2:
        res = df_filtrado[
            df_filtrado['codigo'].str.contains(busca, case=False, na=False) |
            df_filtrado['nome'].str.contains(busca, case=False, na=False)
        ]
        if res.empty:
            st.warning("Nenhum produto encontrado.")
        else:
            for _, p in res.head(6).iterrows():
                with st.expander(f"{p['codigo']} — {p['nome']}"):
                    c1,c2 = st.columns(2)
                    with c1:
                        st.metric("Atual", int(p['estoque_atual']))
                        st.metric("Mín", int(p['estoque_min']))
                        st.metric("Máx", int(p['estoque_max']))
                    with c2:
                        qtd_in = st.number_input("Entrada", min_value=1, value=1, key=f"in_{p['codigo']}")
                        if st.button("+ Entrada", key=f"btn_in_{p['codigo']}"):
                            r = movimentar_estoque(p['codigo'], qtd_in, 'entrada', colab)
                            if r.get('success'): st.success("Entrada realizada (simulada)" if MODO_TESTE else "Entrada realizada!")
                            else: st.error(r.get('message','Erro'))
                        qtd_out = st.number_input("Saída", min_value=1, value=1, key=f"out_{p['codigo']}")
                        if st.button("- Saída", key=f"btn_out_{p['codigo']}"):
                            r = movimentar_estoque(p['codigo'], qtd_out, 'saida', colab)
                            if r.get('success'): st.success("Saída realizada (simulada)" if MODO_TESTE else "Saída realizada!")
                            else: st.error(r.get('message','Erro'))
    else:
        st.info("Digite ao menos 2 caracteres para buscar.")

elif tipo_analise == "Baixa por Faturamento":
    st.subheader("Baixa por Faturamento")
    st.markdown(f"""
<div class="success-box"><strong>Fluxo</strong><br>
1) Upload do arquivo (CSV/XLS/XLSX) com 'Código' e 'Quantidade'<br>
2) Preview: encontrados x não encontrados + estoques finais<br>
3) Botão para {"<b>SIMULAR</b>" if MODO_TESTE else "<b>APLICAR</b>"} baixas
</div>
""", unsafe_allow_html=True)

    colaboradores = ['Pericles','Maria','Camila','Cris VantiStella']
    colab = st.selectbox("Colaborador responsável:", colaboradores, key="colab_fatura")

    up = st.file_uploader("Arquivo de faturamento", type=['csv','xls','xlsx'])
    if up is not None:
        with st.spinner("Processando arquivo..."):
            encontrados, nao_encontrados, erro = processar_faturamento(up, produtos_df)

        if erro:
            st.error(erro)
        else:
            c1,c2,c3 = st.columns(3)
            with c1: st.metric("Total linhas", (len(encontrados)+len(nao_encontrados)))
            with c2: st.metric("Encontrados", len(encontrados))
            with c3: st.metric("Não encontrados", len(nao_encontrados))

            if not nao_encontrados.empty:
                st.markdown('<div class="error-box"><strong>Produtos não encontrados</strong></div>', unsafe_allow_html=True)
                view_nao = nao_encontrados[['codigo','quantidade']].copy()
                view_nao.columns = ['Código','Quantidade']
                st.dataframe(view_nao, use_container_width=True, height=220)
                st.download_button(
                    "📥 Baixar faltantes (CSV)",
                    data=view_nao.to_csv(index=False, encoding='utf-8-sig'),
                    file_name=f"codigos_faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )

            if not encontrados.empty:
                st.markdown("---")
                st.subheader("Preview da baixa")
                prev = encontrados[['codigo','nome','estoque_atual','quantidade','estoque_final']].copy()
                prev.columns = ['Código','Produto','Estoque Atual','Qtd a Baixar','Estoque Final']
                for c in ['Estoque Atual','Qtd a Baixar','Estoque Final']:
                    prev[c] = pd.to_numeric(prev[c], errors='coerce').fillna(0).astype(int)
                prev['Status'] = prev['Estoque Final'].apply(lambda x: 'Negativo' if x<0 else ('Zerado' if x==0 else 'OK'))
                st.dataframe(prev, use_container_width=True, height=420)

                tot = int(prev['Qtd a Baixar'].sum())
                neg = int((prev['Estoque Final']<0).sum())
                zer = int((prev['Estoque Final']==0).sum())
                cc1,cc2,cc3 = st.columns(3)
                with cc1: st.metric("Total a baixar", f"{tot:,}")
                with cc2: st.metric("Ficarão negativos", neg)
                with cc3: st.metric("Ficarão zerados", zer)

                st.markdown("---")
                label_btn = "SIMULAR baixas (modo teste)" if MODO_TESTE else "APLICAR baixas (alterar planilha)"
                if st.button(label_btn, type="primary"):
                    sucessos, erros = 0, 0
                    for _, r in encontrados.iterrows():
                        resp = movimentar_estoque(r['codigo'], r['quantidade'], 'saida', colab)
                        if resp.get('success'): sucessos += 1
                        else: erros += 1
                    if erros==0:
                        st.success(f"Processo concluído: {sucessos} itens {'simulados' if MODO_TESTE else 'atualizados'}.")
                    else:
                        st.warning(f"Concluído com alertas: {sucessos} ok, {erros} erro(s).")
                    st.cache_data.clear()

elif tipo_analise == "Histórico de Baixas":
    st.title("Histórico de Baixas por Faturamento")
    try:
        HIST_URL = "https://docs.google.com/spreadsheets/d/1PpiMQingHf4llA03BiPIuPJPIZqul4grRU_emWDEK1o/gviz/tq?tqx=out:csv&sheet=historico_baixas"
        with st.spinner("Carregando histórico..."):
            r = requests.get(HIST_URL, timeout=15)
            r.raise_for_status()
            dfh = pd.read_csv(StringIO(r.text))
        if dfh.empty:
            st.info("Nenhuma baixa registrada ainda.")
        else:
            st.dataframe(dfh, use_container_width=True, height=520)
            st.download_button(
                "📥 Baixar histórico (CSV)",
                data=dfh.to_csv(index=False, encoding='utf-8-sig'),
                file_name=f"historico_baixas_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    except requests.exceptions.HTTPError:
        st.warning("""⚠️ Aba 'historico_baixas' não encontrada. Crie na planilha com as colunas:
`codigo, nome, qtd_baixada, estoque_anterior, estoque_final, status, data_hora, colaborador`""")
    except Exception as e:
        st.error(f"Erro ao carregar histórico: {e}")

elif tipo_analise == "Relatório de Faltantes":
    st.title("Relatório de Produtos Faltantes")
    up = st.file_uploader("Arquivo de vendas (CSV/XLS/XLSX)", type=['csv','xls','xlsx'])
    if up:
        try:
            name = up.name.lower()
            if name.endswith('.csv'):
                dfv = pd.read_csv(up, encoding='latin1')
            elif name.endswith('.xlsx'):
                dfv = pd.read_excel(up, engine='openpyxl')
            else:
                dfv = pd.read_excel(up, engine='xlrd')
            dfv.columns = [normaliza_coluna(c) for c in dfv.columns]
            if 'codigo' not in dfv.columns or 'quantidade' not in dfv.columns:
                st.error(f"Arquivo precisa de 'codigo' e 'quantidade'. Colunas: {list(dfv.columns)}")
            else:
                dfv['codigo'] = dfv['codigo'].astype(str)
                dfv['quantidade'] = dfv['quantidade'].apply(lambda x: safe_int(x,0)).astype(int)
                dfv = dfv.groupby('codigo', as_index=False)['quantidade'].sum()

                faltas = []
                for _, r in dfv.iterrows():
                    code = normaliza_codigo(r['codigo'])
                    qtd = safe_int(r['quantidade'],0)
                    base = produtos_df[produtos_df['codigo_norm']==code]
                    if base.empty:
                        faltas.append({'Kit Original':'-','Código':code,'Produto':'NÃO CADASTRADO',
                                       'Estoque Atual':0,'Qtd Necessária':qtd,'Falta':qtd,'Tipo':'Produto NÃO cadastrado'})
                        continue
                    p = base.iloc[0]
                    if str(p.get('eh_kit','')).strip().lower()=='sim':
                        comp = [c.strip().upper() for c in str(p.get('componentes','')).split(',') if c and c.strip()]
                        qts  = parse_int_list(p.get('quantidades',''))
                        for c_code, c_q in zip(comp, qts):
                            neces = qtd * safe_int(c_q,0)
                            b2 = produtos_df[produtos_df['codigo_norm']==c_code.upper()]
                            if b2.empty:
                                faltas.append({'Kit Original':code,'Código':c_code,'Produto':'NÃO CADASTRADO',
                                               'Estoque Atual':0,'Qtd Necessária':neces,'Falta':neces,'Tipo':'Componente NÃO cadastrado'})
                            else:
                                est = int(pd.to_numeric(b2.iloc[0]['estoque_atual'], errors='coerce').fillna(0))
                                if est < neces:
                                    faltas.append({'Kit Original':code,'Código':c_code,'Produto':b2.iloc[0]['nome'],
                                                   'Estoque Atual':est,'Qtd Necessária':neces,'Falta':neces-est,'Tipo':'Componente de Kit'})
                    else:
                        est = int(pd.to_numeric(p['estoque_atual'], errors='coerce').fillna(0))
                        if est < qtd:
                            faltas.append({'Kit Original':'-','Código':code,'Produto':p['nome'],
                                           'Estoque Atual':est,'Qtd Necessária':qtd,'Falta':qtd-est,'Tipo':'Produto Normal'})
                if faltas:
                    out = pd.DataFrame(faltas)
                    st.dataframe(out, use_container_width=True, height=520)
                    st.download_button(
                        "📥 Baixar faltantes (CSV)",
                        data=out.to_csv(index=False, encoding='utf-8-sig'),
                        file_name=f"faltantes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                        mime="text/csv"
                    )
                else:
                    st.success("Todos os itens têm estoque suficiente 👏")
        except Exception as e:
            st.error(f"Erro ao processar arquivo: {e}")

# ======================================================
# Footer
# ======================================================
st.markdown("---")
f1,f2,f3 = st.columns(3)
with f1:
    if st.button("🔄 Atualizar dados"):
        st.cache_data.clear()
        st.rerun()
with f2:
    st.write(f"**Última atualização:** {datetime.now().strftime('%H:%M:%S')}")
with f3:
    st.write(f"**Filtros:** {categoria_filtro} | {status_filtro} | {'Simulação' if MODO_TESTE else 'Aplicação real'}")
