def migrate(cr, version):
    """Mark legacy POS orders as Bonuscard not applicable."""
    cr.execute(
        """
        UPDATE pos_order
           SET bonuscard_state = 'not_applicable'
         WHERE bonuscard_state IS NULL
        """
    )
