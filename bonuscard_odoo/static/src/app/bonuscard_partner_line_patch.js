/** @odoo-module */

import { patch } from "@web/core/utils/patch";
import { useService } from "@web/core/utils/hooks";
import { PartnerLine } from "@point_of_sale/app/screens/partner_list/partner_line/partner_line";
import { PartnerList } from "@point_of_sale/app/screens/partner_list/partner_list";

patch(PartnerLine.prototype, {
    setup() {
        const result = super.setup?.(...arguments);
        // Inject services and make them available to the template
        this.bonuscardService = useService("bonuscard_registration");
        this.pos = useService("pos");
        return result;
    },
});

patch(PartnerList.prototype, {
    setup() {
        const result = super.setup?.(...arguments);
        this.bonuscardService = useService("bonuscard_registration");
        this.pos = useService("pos");
        return result;
    },
});
