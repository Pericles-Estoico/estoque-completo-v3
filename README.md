# 📦 Sistema Completo de Controle de Estoque

## 🚀 Visão Geral

Sistema profissional de controle de estoque com integração Google Sheets, semáforos visuais e relatórios para impressão.

### ✨ Funcionalidades Principais

- 📊 **Dashboard em tempo real** com métricas executivas
- 🟢🟡🔴 **Sistema de semáforos** para status visual
- 📋 **3 tipos de relatórios** para impressão
- 🔄 **Integração Google Sheets** para edição colaborativa
- 📱 **Interface responsiva** (mobile-friendly)
- 🎯 **Filtros avançados** por categoria e status
- 💰 **Cálculos automáticos** de valores e ocupação

## 🛠️ Deploy no Streamlit Cloud

### 1. Preparar Repositório GitHub
```bash
# Criar novo repositório no GitHub
# Fazer upload dos arquivos:
# - app.py
# - requirements.txt
# - README.md
```

### 2. Deploy Automático
1. Acesse: https://share.streamlit.io
2. Login com GitHub
3. "New app" → Selecione seu repositório
4. **Main file**: `app.py`
5. Deploy!

## 📊 Configuração Google Sheets

### 1. Estrutura da Planilha
Crie uma planilha com estas colunas **exatas**:

| codigo | nome | categoria | estoque_atual | estoque_min | estoque_max | custo_unitario |
|--------|------|-----------|---------------|-------------|-------------|----------------|
| P001 | Produto A | Eletrônicos | 150 | 50 | 300 | 25.50 |
| P002 | Produto B | Roupas | 30 | 40 | 200 | 15.75 |

### 2. Compartilhar Planilha
- **File** → **Share** → **"Anyone with link can view"**
- Copiar URL completa

### 3. Configurar no Dashboard
- Cole a URL na barra lateral do dashboard
- Clique "Atualizar"

## 🎯 Como Usar

### Dashboard Principal
- **Métricas**: Resumo executivo no topo
- **Tabela**: Produtos com semáforos visuais
- **Filtros**: Por categoria, status ou busca
- **Gráficos**: Distribuição e análises

### Relatórios
1. **Produtos Críticos**: Lista produtos abaixo do estoque mínimo
2. **Relatório Geral**: Visão completa do estoque
3. **Por Categoria**: Análise agrupada por categoria

### Sistema de Semáforos
- 🟢 **Verde (OK)**: Estoque acima de 1,5x o mínimo
- 🟡 **Amarelo (Atenção)**: Entre mínimo e 1,5x mínimo
- 🔴 **Vermelho (Crítico)**: Abaixo do estoque mínimo

## 📋 Template da Planilha

Baixe o template diretamente no dashboard ou use esta estrutura:

```csv
codigo,nome,categoria,estoque_atual,estoque_min,estoque_max,custo_unitario
P001,Produto A,Eletrônicos,150,50,300,25.50
P002,Produto B,Roupas,30,40,200,15.75
P003,Produto C,Casa,80,60,250,32.00
```

## 🔧 Funcionalidades Técnicas

### Cache Inteligente
- Dados atualizados a cada 60 segundos
- Botão de atualização manual
- Auto-refresh opcional

### Validações
- Verificação automática de colunas obrigatórias
- Conversão segura de tipos de dados
- Tratamento de erros de conexão

### Relatórios Avançados
- Cálculo automático de valores
- Percentual de ocupação do estoque
- Valor necessário para reposição
- Export em CSV para Excel

## 📱 Compatibilidade

- ✅ **Desktop**: Todas as funcionalidades
- ✅ **Tablet**: Interface otimizada
- ✅ **Mobile**: Responsivo completo
- ✅ **Navegadores**: Chrome, Firefox, Safari, Edge

## 🚀 Próximos Passos

1. **Deploy** no Streamlit Cloud
2. **Configurar** Google Sheets
3. **Testar** com dados reais
4. **Treinar** equipe para uso
5. **Personalizar** conforme necessidade

## 💡 Dicas de Uso

### Performance
- Mantenha planilha com até 1000 produtos
- Use cache de 60 segundos para otimizar
- Atualize manualmente quando necessário

### Colaboração
- Múltiplos usuários podem editar a planilha
- Use comentários no Google Sheets para comunicação
- Configure notificações por email

### Backup
- Google Sheets faz backup automático
- Exporte relatórios regularmente
- Mantenha histórico de versões

## 🆘 Troubleshooting

### Erro: "Não foi possível carregar planilha"
- ✅ Verifique se planilha está compartilhada publicamente
- ✅ Confirme URL correta (deve conter /spreadsheets/d/)
- ✅ Teste URL no navegador (deve baixar CSV)

### Erro: "Colunas faltando"
- ✅ Verifique nomes exatos das colunas
- ✅ Não use espaços ou acentos nos nomes
- ✅ Primeira linha deve ser cabeçalho

### Dados não atualizam
- ✅ Aguarde até 1 minuto (cache)
- ✅ Clique "Atualizar" no dashboard
- ✅ Verifique se salvou no Google Sheets

## 📞 Suporte

Para dúvidas ou melhorias:
1. Verifique este README
2. Teste com template fornecido
3. Consulte logs de erro no Streamlit

---

**Sistema de Controle de Estoque v2.0**  
*Desenvolvido para máxima eficiência e praticidade*
