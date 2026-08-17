"""
Sample Paradox Database Generator
Creates realistic business test databases with companion .PX primary index files
(Clientes, Produtos, Fornecedores, Vendas, Itens de Venda).
"""

import os
import datetime
from .paradox_engine import ParadoxWriter

def generate_all_samples(output_dir: str = 'samples') -> dict:
    os.makedirs(output_dir, exist_ok=True)
    generated = {}

    # 1. CLIENTES.DB + CLIENTES.PX
    clientes_fields = [
        ('ID_CLIENTE', 4, 4),               # Long (PK)
        ('CNPJ_CPF', 1, 18),                # Alpha(18)
        ('RAZAO_SOCIAL', 1, 60),            # Alpha(60)
        ('NOME_FANTASIA', 1, 40),           # Alpha(40)
        ('LIMITE_CREDITO', 5, 8),           # Currency
        ('ATIVO', 9, 1),                    # Logical
        ('DT_CADASTRO', 2, 4),              # Date
        ('CIDADE', 1, 35),                  # Alpha(35)
        ('UF', 1, 2),                       # Alpha(2)
        ('TELEFONE', 1, 15),                # Alpha(15)
        ('EMAIL', 1, 50),                   # Alpha(50)
    ]
    clientes_rows = [
        (1, '12.345.678/0001-90', 'Alfa Distribuidora de Alimentos Ltda', 'Distribuidora Alfa', 50000.00, True, datetime.date(2022, 1, 15), 'São Paulo', 'SP', '(11) 3456-7890', 'contato@alfaalimentos.com.br'),
        (2, '98.765.432/0001-10', 'Beta Supermercados e Magazine S/A', 'Super Beta', 120000.00, True, datetime.date(2021, 5, 20), 'Campinas', 'SP', '(19) 3211-4455', 'compras@superbeta.com.br'),
        (3, '45.123.789/0001-55', 'Gama Restaurante e Pizzaria ME', 'Pizzaria do Gama', 15000.00, True, datetime.date(2023, 3, 10), 'Belo Horizonte', 'MG', '(31) 3344-5566', 'financeiro@pizzariagama.com'),
        (4, '77.888.999/0001-22', 'Delta Auto Peças e Mecânica Eireli', 'Delta Car Service', 30000.00, True, datetime.date(2022, 8, 5), 'Curitiba', 'PR', '(41) 3022-9988', 'delta@deltacar.com.br'),
        (5, '11.222.333/0001-44', 'Épsilon Materiais de Construção Ltda', 'Épsilon Construções', 80000.00, True, datetime.date(2020, 11, 12), 'Rio de Janeiro', 'RJ', '(21) 2544-1122', 'vendas@epsilonconstroi.com.br'),
        (6, '33.444.555/0001-66', 'Zeta Farmácia e Drogaria Ltda', 'Drogaria Zeta', 25000.00, False, datetime.date(2023, 7, 1), 'Porto Alegre', 'RS', '(51) 3100-2030', 'contato@drogariazeta.com.br'),
        (7, '55.666.777/0001-88', 'Eta Hotelaria e Turismo Eireli', 'Hotel Estrela Dourada', 45000.00, True, datetime.date(2022, 4, 18), 'Salvador', 'BA', '(71) 3200-5050', 'reservas@hotelestrela.com.br'),
        (8, '99.000.111/0001-33', 'Theta Informática e Tecnologia Ltda', 'Theta Byte Info', 60000.00, True, datetime.date(2023, 9, 25), 'Florianópolis', 'SC', '(48) 3399-8877', 'suporte@thetabyte.com.br'),
        (9, '22.333.444/0001-77', 'Iota Moda e Confecções ME', 'Iota Boutique', 18000.00, True, datetime.date(2024, 1, 8), 'Goiânia', 'GO', '(62) 3511-9000', 'atendimento@iotamoda.com.br'),
        (10, '88.999.000/0001-01', 'Kappa Transportes e Logística S/A', 'Kappa Express Log', 150000.00, True, datetime.date(2019, 6, 30), 'Santos', 'SP', '(13) 3288-4000', 'operacoes@kappalog.com.br'),
    ]
    path_clientes = os.path.join(output_dir, 'CLIENTES.DB')
    ParadoxWriter.create_table(path_clientes, 'CLIENTES', clientes_fields, clientes_rows, primary_key_count=1, create_px_index=True)
    generated['CLIENTES.DB'] = {'path': path_clientes, 'records': len(clientes_rows), 'fields': len(clientes_fields)}

    # 2. PRODUTOS.DB + PRODUTOS.PX
    produtos_fields = [
        ('ID_PRODUTO', 4, 4),               # Long (PK)
        ('CODIGO_BARRAS', 1, 14),           # Alpha(14)
        ('DESCRICAO', 1, 60),               # Alpha(60)
        ('UNIDADE', 1, 3),                  # Alpha(3)
        ('PRECO_CUSTO', 5, 8),              # Currency
        ('PRECO_VENDA', 5, 8),              # Currency
        ('ESTOQUE_ATUAL', 6, 8),            # Double
        ('ESTOQUE_MINIMO', 6, 8),           # Double
        ('CATEGORIA', 1, 30),               # Alpha(30)
        ('ATIVO', 9, 1),                    # Logical
    ]
    produtos_rows = [
        (1001, '7891000100101', 'Arroz Agulhinha Tipo 1 Pacote 5kg', 'PCT', 18.50, 26.90, 150.0, 30.0, 'Alimentos', True),
        (1002, '7891000100202', 'Feijão Carioca Nobre 1kg', 'PCT', 5.20, 8.49, 220.0, 50.0, 'Alimentos', True),
        (1003, '7891000100303', 'Azeite de Oliva Extra Virgem 500ml', 'UN', 24.00, 38.90, 45.0, 15.0, 'Alimentos', True),
        (1004, '7892000200404', 'Detergente Líquido Neutro 500ml', 'UN', 1.45, 2.79, 380.0, 80.0, 'Limpeza', True),
        (1005, '7892000200505', 'Sabão em Pó Ação Profunda 1.6kg', 'CX', 11.80, 19.90, 95.0, 20.0, 'Limpeza', True),
        (1006, '7893000300606', 'Refrigerante Cola Zero Lata 350ml', 'UN', 2.10, 4.50, 540.0, 100.0, 'Bebidas', True),
        (1007, '7893000300707', 'Suco Integral de Uva Garrafa 1.5L', 'UN', 9.50, 16.90, 60.0, 15.0, 'Bebidas', True),
        (1008, '7894000400808', 'Café Torrado e Moído Especial 500g', 'PCT', 12.30, 18.75, 180.0, 40.0, 'Alimentos', True),
        (1009, '7895000500909', 'Papel Higiênico Folha Dupla 12 Rolos', 'PCT', 14.00, 22.90, 110.0, 25.0, 'Higiene', True),
        (1010, '7896000601010', 'Óleo de Soja Refinado Garrafa 900ml', 'UN', 4.80, 7.35, 300.0, 60.0, 'Alimentos', True),
        (1011, '7897000701111', 'Leite Integral UHT Caixa 1L', 'CX', 3.40, 5.29, 450.0, 100.0, 'Laticínios', True),
        (1012, '7898000801212', 'Queijo Muçarela Fatiado 500g', 'PCT', 16.50, 27.90, 40.0, 10.0, 'Laticínios', False),
    ]
    path_produtos = os.path.join(output_dir, 'PRODUTOS.DB')
    ParadoxWriter.create_table(path_produtos, 'PRODUTOS', produtos_fields, produtos_rows, primary_key_count=1, create_px_index=True)
    generated['PRODUTOS.DB'] = {'path': path_produtos, 'records': len(produtos_rows), 'fields': len(produtos_fields)}

    # 3. FORNECEDORES.DB + FORNECEDORES.PX
    fornec_fields = [
        ('ID_FORNECEDOR', 4, 4),           # Long (PK)
        ('RAZAO_SOCIAL', 1, 60),
        ('CNPJ', 1, 18),
        ('CIDADE', 1, 35),
        ('UF', 1, 2),
        ('CONTATO', 1, 40),
        ('PRAZO_ENTREGA_DIAS', 3, 2),      # Short
        ('ATIVO', 9, 1),
    ]
    fornec_rows = [
        (1, 'Cerealista Central do Brasil S/A', '01.234.567/0001-89', 'Ribeirão Preto', 'SP', 'Carlos Eduardo Silva', 3, True),
        (2, 'Indústrias Químicas Limpa Mais Ltda', '02.345.678/0001-90', 'Paulínia', 'SP', 'Mariana Alcantara', 5, True),
        (3, 'Engarrafadora de Bebidas do Sul Ltda', '03.456.789/0001-01', 'Caxias do Sul', 'RS', 'Roberto Fagundes', 7, True),
        (4, 'Laticínios Vale Verde ME', '04.567.890/0001-12', 'Passos', 'MG', 'Ana Paula Castro', 2, True),
    ]
    path_fornec = os.path.join(output_dir, 'FORNECEDORES.DB')
    ParadoxWriter.create_table(path_fornec, 'FORNECEDORES', fornec_fields, fornec_rows, primary_key_count=1, create_px_index=True)
    generated['FORNECEDORES.DB'] = {'path': path_fornec, 'records': len(fornec_rows), 'fields': len(fornec_fields)}

    # 4. VENDAS.DB + VENDAS.PX
    vendas_fields = [
        ('ID_VENDA', 4, 4),                 # Long (PK)
        ('NUM_PEDIDO', 4, 4),
        ('DT_EMISSAO', 2, 4),
        ('ID_CLIENTE', 4, 4),
        ('VALOR_BRUTO', 5, 8),
        ('DESCONTO', 5, 8),
        ('VALOR_LIQUIDO', 5, 8),
        ('FORMA_PAGTO', 1, 20),
        ('STATUS', 1, 15),
    ]
    vendas_rows = [
        (1, 5001, datetime.date(2024, 5, 2), 1, 1450.00, 50.00, 1400.00, 'BOLETO 30 DIAS', 'FATURADO'),
        (2, 5002, datetime.date(2024, 5, 3), 2, 8900.50, 200.50, 8700.00, 'PIX', 'FATURADO'),
        (3, 5003, datetime.date(2024, 5, 5), 3, 620.00, 0.00, 620.00, 'CARTAO CREDITO', 'PAGO'),
        (4, 5004, datetime.date(2024, 5, 8), 4, 3450.80, 100.00, 3350.80, 'BOLETO 15 DIAS', 'FATURADO'),
        (5, 5005, datetime.date(2024, 5, 12), 5, 12500.00, 500.00, 12000.00, 'TRANSFERENCIA', 'PENDENTE'),
        (6, 5006, datetime.date(2024, 5, 15), 1, 2890.40, 90.40, 2800.00, 'BOLETO 30 DIAS', 'FATURADO'),
        (7, 5007, datetime.date(2024, 5, 18), 7, 750.00, 0.00, 750.00, 'PIX', 'PAGO'),
        (8, 5008, datetime.date(2024, 5, 20), 8, 4120.00, 120.00, 4000.00, 'CARTAO PARCELADO', 'PAGO'),
    ]
    path_vendas = os.path.join(output_dir, 'VENDAS.DB')
    ParadoxWriter.create_table(path_vendas, 'VENDAS', vendas_fields, vendas_rows, primary_key_count=1, create_px_index=True)
    generated['VENDAS.DB'] = {'path': path_vendas, 'records': len(vendas_rows), 'fields': len(vendas_fields)}

    # 5. ITENS_VENDA.DB + ITENS_VENDA.PX (Chave composta ID_ITEM + ID_VENDA ou ID_ITEM)
    itens_fields = [
        ('ID_ITEM', 4, 4),                  # Long (PK 1)
        ('ID_VENDA', 4, 4),                 # Long (PK 2)
        ('ID_PRODUTO', 4, 4),
        ('QUANTIDADE', 6, 8),
        ('VALOR_UNITARIO', 5, 8),
        ('SUBTOTAL', 5, 8),
        ('DESCONTO', 5, 8),
        ('TOTAL_ITEM', 5, 8),
    ]
    itens_rows = [
        (1, 1, 1001, 30.0, 26.90, 807.00, 7.00, 800.00),
        (2, 1, 1002, 50.0, 8.49, 424.50, 4.50, 420.00),
        (3, 1, 1006, 40.0, 4.50, 180.00, 0.00, 180.00),
        (4, 2, 1001, 200.0, 26.90, 5380.00, 100.00, 5280.00),
        (5, 2, 1003, 50.0, 38.90, 1945.00, 45.00, 1900.00),
        (6, 2, 1008, 80.0, 18.75, 1500.00, 0.00, 1500.00),
        (7, 3, 1007, 20.0, 16.90, 338.00, 0.00, 338.00),
        (8, 3, 1006, 60.0, 4.50, 270.00, 0.00, 270.00),
        (9, 4, 1004, 300.0, 2.79, 837.00, 37.00, 800.00),
        (10, 4, 1005, 100.0, 19.90, 1990.00, 40.00, 1950.00),
        (11, 4, 1009, 30.0, 22.90, 687.00, 23.00, 664.00),
    ]
    path_itens = os.path.join(output_dir, 'ITENS_VENDA.DB')
    # ITENS_VENDA uses composite primary key (ID_ITEM, ID_VENDA)
    ParadoxWriter.create_table(path_itens, 'ITENS_VENDA', itens_fields, itens_rows, primary_key_count=2, create_px_index=True)
    generated['ITENS_VENDA.DB'] = {'path': path_itens, 'records': len(itens_rows), 'fields': len(itens_fields)}

    return generated
