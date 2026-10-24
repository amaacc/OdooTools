import os
import sys
import re
import xmlrpc.client
from typing import Dict, List, Optional, Tuple, Any

# Ensure current and parent directory are in sys.path to access security.py
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for p in (current_dir, parent_dir):
    if p not in sys.path:
        sys.path.insert(0, p)

try:
    from security import get_odoo_credentials
except Exception as e:
    get_odoo_credentials = None
    print(f"[OdooVerifier] Failed to import get_odoo_credentials: {e}")


class OdooVerifier:
    """
    Live Odoo 17 verification engine for products, categories, tags,
    existing barcodes, and internal reference sequence numbering.
    """

    def __init__(self, url: str = None, db: str = None, username: str = None, password: str = None):
        self.last_error = ""
        if not all([url, db, username, password]):
            if get_odoo_credentials:
                try:
                    self.url, self.db, self.username, self.password = get_odoo_credentials()
                except Exception as e:
                    self.last_error = f"خطأ في فك تشفير بيانات أودو: {e}"
                    print(f"[OdooVerifier] {self.last_error}")
                    self.url = url or ""
                    self.db = db or ""
                    self.username = username or ""
                    self.password = password or ""
            else:
                self.last_error = "وحدة الأمان security.py أو get_odoo_credentials غير متوفرة."
                self.url = url or ""
                self.db = db or ""
                self.username = username or ""
                self.password = password or ""
        else:
            self.url = url or ""
            self.db = db or ""
            self.username = username or ""
            self.password = password or ""

        self.uid: Optional[int] = None
        self._categories_cache: Optional[Dict[str, Any]] = None
        self._tags_cache: Optional[Dict[str, Any]] = None

    def authenticate(self) -> bool:
        """Authenticates with Odoo XML-RPC API."""
        if not self.url or not self.db or not self.username or not self.password:
            if not self.last_error:
                self.last_error = "بيانات الاتصال بأودو مفقودة أو غير مكتملة."
            return False
        try:
            common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common", allow_none=True)
            uid = common.authenticate(self.db, self.username, self.password, {})
            if isinstance(uid, int) and uid > 0:
                self.uid = uid
                self.last_error = ""
                return True
            self.last_error = "فشل المصادقة مع سيرفر أودو (تحقق من اسم المستخدم أو كلمة المرور)."
            return False
        except Exception as e:
            self.last_error = f"تعذر الاتصال بسيرفر أودو: {e}"
            print(f"[OdooVerifier] Authentication error: {e}")
            return False

    def _get_models(self):
        if not self.uid and not self.authenticate():
            raise ConnectionError("Failed to authenticate with Odoo server.")
        return xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object", allow_none=True)

    def get_all_categories(self, refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches all product categories from Odoo and indexes them
        by name, complete_name, and code for case-insensitive lookup.
        """
        if self._categories_cache is not None and not refresh:
            return self._categories_cache

        models = self._get_models()
        cats = models.execute_kw(
            self.db, self.uid, self.password,
            'product.category', 'search_read',
            [[]],
            {'fields': ['id', 'name', 'complete_name']}
        )

        mapping = {}
        for c in cats:
            name = c.get('name') or ''
            comp_name = c.get('complete_name') or ''
            cid = c.get('id')
            data = {'id': cid, 'name': name, 'complete_name': comp_name}

            # Index by lower case name and complete name
            if name:
                mapping[name.strip().lower()] = data
                # If name starts with code (e.g. SCP-Skin Care), also index by code (SCP)
                code_match = re.match(r'^([A-Z0-9]+)[-\s]', name)
                if code_match:
                    mapping[code_match.group(1).lower()] = data

            if comp_name:
                mapping[comp_name.strip().lower()] = data

        self._categories_cache = mapping
        return mapping

    def get_category_names_list(self) -> List[str]:
        """
        Returns sorted list of unique category complete names or names from Odoo.
        """
        try:
            mapping = self.get_all_categories()
            names = set()
            for d in mapping.values():
                n = d.get('complete_name') or d.get('name')
                if n:
                    names.add(n)
            if names:
                return sorted(list(names))
        except Exception as e:
            print(f"[OdooVerifier] get_category_names_list error: {e}")
        return []

    def get_all_tags(self, refresh: bool = False) -> Dict[str, Any]:
        """
        Fetches all product tags from Odoo and indexes them
        by name and code for case-insensitive lookup.
        """
        if self._tags_cache is not None and not refresh:
            return self._tags_cache

        models = self._get_models()
        tags = models.execute_kw(
            self.db, self.uid, self.password,
            'product.tag', 'search_read',
            [[]],
            {'fields': ['id', 'name']}
        )

        mapping = {}
        for t in tags:
            name = t.get('name') or ''
            tid = t.get('id')
            data = {'id': tid, 'name': name}

            if name:
                mapping[name.strip().lower()] = data
                # If tag starts with code (e.g. SG0040-OTHER PRODUCTS), also index by code
                code_match = re.match(r'^([A-Z0-9]+)[-\s]', name)
                if code_match:
                    mapping[code_match.group(1).lower()] = data

        self._tags_cache = mapping
        return mapping

    def check_existing_products_by_barcodes(self, barcodes: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Checks a list of barcodes against Odoo:
        1. product.product primary barcode
        2. product.packaging barcode
        Returns a dict mapping barcode -> details of existing product in Odoo.
        """
        clean_barcodes = list(set(b.strip() for b in barcodes if b and str(b).strip()))
        if not clean_barcodes:
            return {}

        models = self._get_models()
        found_products: Dict[str, Dict[str, Any]] = {}

        # 1. Search primary barcodes in product.product
        batch_size = 500
        for i in range(0, len(clean_barcodes), batch_size):
            batch = clean_barcodes[i:i + batch_size]
            domain = [['barcode', 'in', batch]]
            fields = ['id', 'name', 'display_name', 'barcode', 'default_code', 'standard_price', 'list_price', 'categ_id', 'product_name_arabic', 'qty_available', 'product_tmpl_id', 'create_uid', 'create_date']
            prods = models.execute_kw(
                self.db, self.uid, self.password,
                'product.product', 'search_read',
                [domain],
                {'fields': fields}
            )

            # Also fetch Arabic names using Arabic language context as secondary fallback
            prod_ids = [p['id'] for p in prods]
            ar_names = {}
            if prod_ids:
                try:
                    ar_prods = models.execute_kw(
                        self.db, self.uid, self.password,
                        'product.product', 'read',
                        [prod_ids],
                        {'fields': ['name'], 'context': {'lang': 'ar_001'}}
                    )
                    for ap in ar_prods:
                        ar_names[ap['id']] = ap.get('name') or ''
                except Exception:
                    pass

            for p in prods:
                bc = (p.get('barcode') or '').strip()
                if bc:
                    pid = p['id']
                    raw_en = (p.get('name') or '').strip()
                    # Priority: custom field product_name_arabic, then ar_001 translation
                    raw_ar = (p.get('product_name_arabic') or '').strip()
                    if not raw_ar:
                        raw_ar = (ar_names.get(pid) or '').strip()

                    categ_arr = p.get('categ_id') or []
                    categ_name = categ_arr[1] if isinstance(categ_arr, (list, tuple)) and len(categ_arr) > 1 else ''

                    tmpl_arr = p.get('product_tmpl_id') or []
                    tmpl_id = tmpl_arr[0] if isinstance(tmpl_arr, (list, tuple)) and len(tmpl_arr) > 0 else None

                    c_uid_arr = p.get('create_uid')
                    created_by = c_uid_arr[1] if isinstance(c_uid_arr, (list, tuple)) and len(c_uid_arr) > 1 else ''
                    c_date_raw = str(p.get('create_date') or '')
                    c_date = c_date_raw[:16] if len(c_date_raw) >= 16 else c_date_raw

                    found_products[bc] = {
                        'id': pid,
                        'tmpl_id': tmpl_id,
                        'odoo_id': '',
                        'barcode': bc,
                        'default_code': p.get('default_code') or '',
                        'name_en': raw_en,
                        'name_ar': raw_ar,
                        'cost': float(p.get('standard_price') or 0.0),
                        'price': float(p.get('list_price') or 0.0),
                        'qty_available': float(p.get('qty_available') or 0.0),
                        'category': categ_name,
                        'created_by': created_by,
                        'create_date': c_date,
                        'source': 'product.product'
                    }

        # 2. Search remaining barcodes in product.packaging
        remaining_barcodes = [b for b in clean_barcodes if b not in found_products]
        for i in range(0, len(remaining_barcodes), batch_size):
            batch = remaining_barcodes[i:i + batch_size]
            pkg_domain = [['barcode', 'in', batch]]
            pkgs = models.execute_kw(
                self.db, self.uid, self.password,
                'product.packaging', 'search_read',
                [pkg_domain],
                {'fields': ['barcode', 'product_id']}
            )

            pkg_prod_ids = []
            pkg_map = {}
            for pkg in pkgs:
                p_arr = pkg.get('product_id')
                if p_arr and isinstance(p_arr, (list, tuple)) and len(p_arr) > 0:
                    pid = p_arr[0]
                    bc = (pkg.get('barcode') or '').strip()
                    pkg_map[bc] = pid
                    pkg_prod_ids.append(pid)

            if pkg_prod_ids:
                pkg_prods = models.execute_kw(
                    self.db, self.uid, self.password,
                    'product.product', 'read',
                    [list(set(pkg_prod_ids))],
                    {'fields': ['id', 'name', 'default_code', 'standard_price', 'list_price', 'categ_id', 'product_name_arabic', 'qty_available', 'product_tmpl_id', 'create_uid', 'create_date']}
                )
                prod_lookup = {p['id']: p for p in pkg_prods}

                for bc, pid in pkg_map.items():
                    if pid in prod_lookup:
                        p = prod_lookup[pid]
                        categ_arr = p.get('categ_id') or []
                        categ_name = categ_arr[1] if isinstance(categ_arr, (list, tuple)) and len(categ_arr) > 1 else ''
                        tmpl_arr = p.get('product_tmpl_id') or []
                        tmpl_id = tmpl_arr[0] if isinstance(tmpl_arr, (list, tuple)) and len(tmpl_arr) > 0 else None
                        c_uid_arr = p.get('create_uid')
                        created_by = c_uid_arr[1] if isinstance(c_uid_arr, (list, tuple)) and len(c_uid_arr) > 1 else ''
                        c_date_raw = str(p.get('create_date') or '')
                        c_date = c_date_raw[:16] if len(c_date_raw) >= 16 else c_date_raw
                        found_products[bc] = {
                            'id': pid,
                            'tmpl_id': tmpl_id,
                            'odoo_id': '',
                            'barcode': bc,
                            'default_code': p.get('default_code') or '',
                            'name_en': (p.get('name') or '').strip(),
                            'name_ar': (p.get('product_name_arabic') or '').strip(),
                            'cost': float(p.get('standard_price') or 0.0),
                            'price': float(p.get('list_price') or 0.0),
                            'qty_available': float(p.get('qty_available') or 0.0),
                            'category': categ_name,
                            'created_by': created_by,
                            'create_date': c_date,
                            'source': 'product.packaging'
                        }

        # 3. Batch fetch Odoo External IDs (id) for all found product templates
        tmpl_ids = list(set(p['tmpl_id'] for p in found_products.values() if p.get('tmpl_id')))
        if tmpl_ids:
            tmpl_to_ext = {}
            try:
                batch_size_exp = 500
                for i in range(0, len(tmpl_ids), batch_size_exp):
                    batch = tmpl_ids[i:i + batch_size_exp]
                    res = models.execute_kw(
                        self.db, self.uid, self.password,
                        'product.template', 'export_data',
                        [batch, ['id']]
                    )
                    datas = res.get('datas', [])
                    for tid, row in zip(batch, datas):
                        if row and row[0]:
                            tmpl_to_ext[tid] = row[0]
            except Exception as e:
                print(f"[OdooVerifier] Warning: export_data on product.template failed: {e}")
                try:
                    ir_records = models.execute_kw(
                        self.db, self.uid, self.password,
                        'ir.model.data', 'search_read',
                        [[['model', '=', 'product.template'], ['res_id', 'in', tmpl_ids]]],
                        {'fields': ['res_id', 'complete_name']}
                    )
                    for r in ir_records:
                        tmpl_to_ext[r['res_id']] = r.get('complete_name') or ''
                except Exception as e2:
                    print(f"[OdooVerifier] Warning: ir.model.data fallback also failed: {e2}")

            for p in found_products.values():
                tid = p.get('tmpl_id')
                if tid and tid in tmpl_to_ext:
                    p['odoo_id'] = tmpl_to_ext[tid]
                elif tid:
                    p['odoo_id'] = f"__export__.product_template_{tid}"

        return found_products

    def get_highest_internal_reference_sequence(self, prefix: str) -> int:
        """
        Finds the highest existing sequence number for a given prefix in Odoo.
        Example: for prefix '4101-8', searches codes like '4101-827270'.
        Extracts the numeric suffix after prefix (e.g. 27270) and returns the max int.
        """
        models = self._get_models()
        clean_prefix = prefix.strip()
        pattern = f"{clean_prefix}%"

        prods = models.execute_kw(
            self.db, self.uid, self.password,
            'product.product', 'search_read',
            [[['default_code', '=like', pattern]]],
            {'fields': ['default_code'], 'limit': 150, 'order': 'default_code desc'}
        )

        max_seq = 0
        for p in prods:
            code = (p.get('default_code') or '').strip()
            if code.startswith(clean_prefix):
                suffix = code[len(clean_prefix):]
                # extract contiguous digits
                digits = "".join(c for c in suffix if c.isdigit())
                if digits:
                    val = int(digits)
                    if val > max_seq:
                        max_seq = val

        return max_seq

    def resolve_vendor(self, query: str) -> Dict[str, Any]:
        """
        Resolves a vendor code or name by searching:
        1. product.tag in Odoo: tags starting with code (e.g. '905-315 AlArkan Alsehhiya Company')
        2. res.partner in Odoo: partners with ref == query or name ilike query
        Returns a dict:
        {
            'success': bool,
            'source': 'product.tag' | 'res.partner' | 'none',
            'tag_name': str,          # e.g. '905-315 AlArkan Alsehhiya Company'
            'supplier_no': str,       # e.g. '905-315'
            'supplier_name': str,     # e.g. 'AlArkan Alsehhiya Company'
            'partner_id': Optional[int],
            'tag_id': Optional[int],
            'is_tag_in_odoo': bool    # True if already in product.tag
        }
        """
        clean = (query or '').strip()
        if not clean:
            return {
                'success': False,
                'source': 'none',
                'tag_name': '',
                'supplier_no': '',
                'supplier_name': '',
                'partner_id': None,
                'tag_id': None,
                'is_tag_in_odoo': False
            }

        # Clean query if it has extension
        clean = re.sub(r'\.(xlsx|xls|csv)$', '', clean, flags=re.IGNORECASE).strip()

        if not self.authenticate():
            return {
                'success': False,
                'source': 'offline',
                'tag_name': clean,
                'supplier_no': clean,
                'supplier_name': '',
                'partner_id': None,
                'tag_id': None,
                'is_tag_in_odoo': False
            }

        models = self._get_models()

        # 1. Search in product.tag
        try:
            tags = models.execute_kw(
                self.db, self.uid, self.password,
                'product.tag', 'search_read',
                [[['name', 'ilike', clean]]],
                {'fields': ['id', 'name'], 'limit': 20}
            )
            if tags:
                clean_tags = [t for t in tags if '(copy)' not in t['name'].lower()]
                best = clean_tags[0] if clean_tags else tags[0]
                full_tag = best['name'].strip()

                m = re.match(r'^\[?([A-Za-z0-9\-_]+)\]?\s+(.*)$', full_tag)
                if m:
                    s_no = m.group(1).strip()
                    s_name = m.group(2).strip()
                else:
                    s_no = clean
                    s_name = full_tag

                return {
                    'success': True,
                    'source': 'product.tag',
                    'tag_name': full_tag,
                    'supplier_no': s_no,
                    'supplier_name': s_name,
                    'partner_id': None,
                    'tag_id': best['id'],
                    'is_tag_in_odoo': True
                }
        except Exception as e:
            print(f"[OdooVerifier] resolve_vendor product.tag search error: {e}")

        # 2. Search in res.partner
        try:
            domain = ['|', ['ref', '=', clean], ['name', 'ilike', clean]]
            partners = models.execute_kw(
                self.db, self.uid, self.password,
                'res.partner', 'search_read',
                [domain],
                {'fields': ['id', 'ref', 'name', 'supplier_rank'], 'limit': 10}
            )
            if partners:
                sorted_p = sorted(partners, key=lambda x: x.get('supplier_rank') or 0, reverse=True)
                p = sorted_p[0]
                p_ref = str(p.get('ref') or '').strip()
                p_name = str(p.get('name') or '').strip()
                s_no = p_ref if p_ref else clean
                s_name = p_name
                full_tag = f"{s_no} {s_name}".strip()

                tag_chk = models.execute_kw(
                    self.db, self.uid, self.password,
                    'product.tag', 'search_read',
                    [[['name', '=ilike', full_tag]]],
                    {'fields': ['id', 'name'], 'limit': 1}
                )
                tag_id = tag_chk[0]['id'] if tag_chk else None

                return {
                    'success': True,
                    'source': 'res.partner',
                    'tag_name': full_tag,
                    'supplier_no': s_no,
                    'supplier_name': s_name,
                    'partner_id': p['id'],
                    'tag_id': tag_id,
                    'is_tag_in_odoo': tag_id is not None
                }
        except Exception as e:
            print(f"[OdooVerifier] resolve_vendor res.partner search error: {e}")

        return {
            'success': False,
            'source': 'none',
            'tag_name': clean,
            'supplier_no': clean,
            'supplier_name': '',
            'partner_id': None,
            'tag_id': None,
            'is_tag_in_odoo': False
        }
