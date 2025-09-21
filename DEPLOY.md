# 🚀 Guia de Deploy - Passo a Passo

## 📋 CHECKLIST COMPLETO

### ✅ Arquivos Necessários
- [ ] `app.py` (aplicação principal)
- [ ] `requirements.txt` (dependências)
- [ ] `README.md` (documentação)
- [ ] `DEPLOY.md` (este guia)

## 🔥 DEPLOY RÁPIDO (5 MINUTOS)

### 1️⃣ GitHub (2 minutos)
1. **Criar repositório**: github.com → "New repository"
2. **Nome**: `sistema-estoque-v2`
3. **Upload arquivos**: Arrastar os 4 arquivos
4. **Commit**: "Sistema completo de estoque"

### 2️⃣ Streamlit Cloud (2 minutos)
1. **Acessar**: share.streamlit.io
2. **Login**: GitHub
3. **New app**: Selecionar repositório
4. **Main file**: `app.py` ← **IMPORTANTE!**
5. **Deploy**: Aguardar 1-2 minutos

### 3️⃣ Google Sheets (1 minuto)
1. **Criar planilha**: sheets.google.com
2. **Colunas**: `codigo | nome | categoria | estoque_atual | estoque_min | estoque_max | custo_unitario`
3. **Compartilhar**: "Anyone with link can view"
4. **Copiar URL**: URL completa da planilha

## 📊 CONFIGURAÇÃO DETALHADA

### Google Sheets - Estrutura Exata

```
A1: codigo
B1: nome  
C1: categoria
D1: estoque_atual
E1: estoque_min
F1: estoque_max
G1: custo_unitario
```

### Dados de Exemplo
```
A2: P001    B2: Produto A    C2: Eletrônicos    D2: 150    E2: 50     F2: 300    G2: 25.50
A3: P002    B3: Produto B    C3: Roupas         D3: 30     E3: 40     F3: 200    G3: 15.75
A4: P003    B4: Produto C    C4: Casa           D4: 80     E4: 60     F4: 250    G4: 32.00
```

### Compartilhamento
1. **Botão "Share"** (canto superior direito)
2. **"Change to anyone with the link"**
3. **Permissão**: "Viewer"
4. **"Copy link"**

## 🎯 TESTE FINAL

### 1. Verificar Deploy
- [ ] App carregou sem erros
- [ ] Interface aparece corretamente
- [ ] Sidebar visível com configuração

### 2. Testar Conexão
- [ ] Colar URL do Google Sheets
- [ ] Clicar "Atualizar"
- [ ] Dados aparecem na tabela
- [ ] Semáforos funcionando

### 3. Testar Relatórios
- [ ] Botão "Produtos Críticos" funciona
- [ ] Botão "Relatório Geral" funciona
- [ ] Botão "Por Categoria" funciona
- [ ] Downloads CSV funcionam

## 🔧 TROUBLESHOOTING

### ❌ App não carrega
**Problema**: Erro no Streamlit Cloud
**Solução**: 
- Verificar logs no Streamlit
- Confirmar `app.py` como main file
- Verificar `requirements.txt`

### ❌ "Colunas faltando"
**Problema**: Estrutura da planilha incorreta
**Solução**:
- Verificar nomes exatos das colunas
- Sem espaços ou acentos
- Primeira linha = cabeçalho

### ❌ "Erro ao carregar planilha"
**Problema**: Permissões ou URL incorreta
**Solução**:
- Planilha deve estar pública
- URL completa (com /spreadsheets/d/)
- Testar URL no navegador

### ❌ Dados não aparecem
**Problema**: Cache ou conexão
**Solução**:
- Aguardar 1 minuto
- Clicar "Atualizar"
- Verificar internet

## 🚀 OTIMIZAÇÕES

### Performance
```python
# Cache configurado para 60 segundos
@st.cache_data(ttl=60)

# Timeout de 10 segundos para requests
requests.get(csv_url, timeout=10)
```

### Segurança
- Planilha somente leitura
- Sem dados sensíveis expostos
- HTTPS automático no Streamlit

### Escalabilidade
- Suporta até 1000 produtos
- Cache inteligente
- Interface responsiva

## 📱 ACESSO MOBILE

### Configuração Automática
- Layout responsivo
- Botões touch-friendly
- Tabelas scrolláveis
- Gráficos adaptáveis

### Teste Mobile
1. Abrir app no celular
2. Verificar sidebar funciona
3. Testar botões de relatório
4. Confirmar downloads

## 🎉 RESULTADO FINAL

### O que você terá:
- ✅ **Dashboard profissional** online
- ✅ **URL pública** para compartilhar
- ✅ **Edição colaborativa** via Google Sheets
- ✅ **Relatórios automáticos** para impressão
- ✅ **Sistema de alertas** visuais
- ✅ **Acesso mobile** completo

### Próximos passos:
1. **Treinar equipe** para usar Google Sheets
2. **Configurar alertas** por email (opcional)
3. **Personalizar categorias** conforme negócio
4. **Adicionar mais produtos** na planilha
5. **Monitorar uso** e performance

## 💡 DICAS PRO

### Automação
- Use Google Apps Script para regras avançadas
- Configure Zapier para integrações
- Adicione webhooks para notificações

### Backup
- Google Sheets faz backup automático
- Exporte relatórios semanalmente
- Mantenha histórico de versões

### Colaboração
- Adicione comentários na planilha
- Use cores para destacar produtos
- Configure notificações de edição

---

**🎯 DEPLOY COMPLETO EM 5 MINUTOS!**  
*Sistema profissional sem instalar nada localmente*
