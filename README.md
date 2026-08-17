# Paradox2Firebird Studio v2.0

**Paradox2Firebird Studio** é uma ferramenta de ponta para migração e conversão de bancos de dados legados **Borland Paradox** (`.DB`, `.MB`, `.PX`) para **Firebird SQL** (`.FDB` / `.SQL`).

---

## 🚀 Principais Recursos

1. **Motor de Leitura Binária Paradox Nativo (Pure Python):**
   - Independente do BDE (Borland Database Engine) de 32 bits.
   - Suporte completo a formatos Paradox 3.x, 4.x, 5.x e 7.x.
   - Decodificação de todos os tipos de dados: Alpha (VARCHAR), Long/AutoInc (INTEGER/BIGINT), Currency/Double (NUMERIC/DOUBLE PRECISION), Date, Time, Timestamp, Logical (BOOLEAN) e BLOBs.

2. **Leitura e Tratamento dos Arquivos de Índice `.PX`:**
   - Detecta e decodifica os arquivos de índice primário `.PX`.
   - Mapeia chaves primárias simples e compostas automaticamente no Firebird (`CONSTRAINT PK_TABELA PRIMARY KEY (...)`).

3. **Geração do Banco de Dados `.FDB` com 1 Clique:**
   - Cria o arquivo físico `.FDB` compilando as tabelas Paradox selecionadas em um único banco relacional.
   - Compatível com Firebird 2.5, 3.0, 4.0 e 5.0.

4. **Multi-Seleção de Tabelas:**
   - Escolha exatamente quais tabelas deseja consolidar no mesmo `.FDB`.

5. **Importação e Exportação de CSV:**
   - Exporta tabelas para `.CSV` (UTF-8 com BOM, 100% compatível com Excel) ou pacote `.ZIP`.
   - Importa planilhas `.CSV` com inferência inteligente de tipos de dados.

6. **Interface Web Moderna e Responsiva:**
   - Visualizador de dados (*Data Grid*) com pesquisa instantânea e filtros.
   - Editor de mapeamento de tipos DDL.
   - Visualizador de scripts SQL com realce de sintaxe.
   - Barra superior com abas horizontais e modo tela cheia.

---

## 💻 Como Usar

1. Execute o atalho **Paradox2Firebird Studio** na sua Área de Trabalho ou Menu Iniciar.
2. A aplicação iniciará o servidor local e abrirá automaticamente o painel no seu navegador (`http://127.0.0.1:5000`).
3. Arraste suas tabelas Paradox (`.DB`, `.PX`) ou utilize as bases de teste incluídas.
4. Clique em **`🔥 Gerar Banco .FDB`** para compilar seu novo banco de dados Firebird!

---

*Desenvolvido com tecnologia Connect Software.*
