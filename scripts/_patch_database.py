"""One-time patch: add CDI sensitivity columns to SnapshotDecisions in database.py."""
import pathlib

p = pathlib.Path("src/fii_analysis/data/database.py")
content = p.read_text(encoding="utf-8")

old = "    dias_ate_proxima_data_com: Mapped[int | None] = mapped_column(Integer)\n\n    # Auditoria"
new = """    dias_ate_proxima_data_com: Mapped[int | None] = mapped_column(Integer)

    # CDI Sensitivity (diagnostico V1 - NAO altera acao)
    cdi_status: Mapped[str | None] = mapped_column(String)
    cdi_beta: Mapped[float | None] = mapped_column(Numeric)
    cdi_r_squared: Mapped[float | None] = mapped_column(Numeric)
    cdi_p_value: Mapped[float | None] = mapped_column(Numeric)
    cdi_residuo_atual: Mapped[float | None] = mapped_column(Numeric)
    cdi_residuo_percentil: Mapped[float | None] = mapped_column(Numeric)

    # Auditoria"""

if old in content:
    content = content.replace(old, new, 1)
    p.write_text(content, encoding="utf-8")
    print(f"DONE - replaced. New length: {len(content)} chars")
else:
    print("NOT FOUND - checking what is around dias_ate...")
    idx = content.find("dias_ate_proxima_data_com")
    if idx >= 0:
        print(repr(content[idx-10:idx+300]))
    else:
        print("dias_ate_proxima_data_com not found at all!")