# OpenSayo v1.15 — Full window and popup call-site inventory

Source file: `OpenSayo/py/opensayo_v019_alpha22.py`. Line numbers are generated from the actual packaged file.

**Inventory:** 11 Tk secondary windows, 41 file/name pickers, 150 message/confirmation call sites — 202 call sites total (plus the main application window).

Repeated access should focus an existing persistent window, not open duplicates. Pickers and dialogs should open only once per deliberate user action, cancel cleanly, and never program hardware without confirmation.

These identifiers describe source call sites, not user records.

## Window call sites (11)

| ID | Source method | API | Line |
|---|---|---|---:|
| W001 | `_edit_navigate_keys` | `tk.Toplevel` | 1573 |
| W002 | `_dropdown_import` | `tk.Toplevel` | 1730 |
| W003 | `_show_help` | `tk.Toplevel` | 2214 |
| W004 | `enter` | `tk.Toplevel` | 2503 |
| W005 | `_show_about` | `tk.Toplevel` | 2519 |
| W006 | `settings` | `tk.Toplevel` | 3625 |
| W007 | `open_form_preview` | `tk.Toplevel` | 3805 |
| W008 | `_open_grid_mode` | `tk.Toplevel` | 3989 |
| W009 | `_open_manage_fields` | `tk.Toplevel` | 4110 |
| W010 | `_eight_device_management` | `tk.Toplevel` | 4835 |
| W011 | `_open_recorder` | `tk.Toplevel` | 5880 |

## Picker call sites (41)

| ID | Source method | API | Line |
|---|---|---|---:|
| P001 | `_dropdown_create` | `simpledialog.askstring` | 1685 |
| P002 | `_dropdown_export` | `filedialog.asksaveasfilename` | 1707 |
| P003 | `_dropdown_import` | `filedialog.askopenfilename` | 1714 |
| P004 | `_definitions_export_json` | `filedialog.asksaveasfilename` | 1845 |
| P005 | `_definitions_import_json` | `filedialog.askopenfilename` | 1853 |
| P006 | `_macro_open` | `filedialog.askopenfilename` | 2928 |
| P007 | `_macro_save` | `filedialog.asksaveasfilename` | 2943 |
| P008 | `_macro_save_readable` | `filedialog.asksaveasfilename` | 2953 |
| P009 | `_workspace_save` | `filedialog.asksaveasfilename` | 3231 |
| P010 | `_workspace_open` | `filedialog.askopenfilename` | 3266 |
| P011 | `_workspace_export_script` | `filedialog.asksaveasfilename` | 3288 |
| P012 | `_workspace_import_script` | `filedialog.askopenfilename` | 3298 |
| P013 | `_export_form_format` | `filedialog.asksaveasfilename` | 3366 |
| P014 | `_import_form_format` | `filedialog.askopenfilename` | 3380 |
| P015 | `_save_form_layout` | `filedialog.asksaveasfilename` | 3425 |
| P016 | `_load_form_layout` | `filedialog.askopenfilename` | 3433 |
| P017 | `_save_field_list` | `filedialog.asksaveasfilename` | 3451 |
| P018 | `_load_field_list` | `filedialog.askopenfilename` | 3465 |
| P019 | `save_as` | `filedialog.asksaveasfilename` | 3610 |
| P020 | `open_project` | `filedialog.askopenfilename` | 3614 |
| P021 | `_designer_add_label` | `simpledialog.askstring` | 4052 |
| P022 | `_designer_rename` | `simpledialog.askstring` | 4336 |
| P023 | `_designer_add` | `simpledialog.askstring` | 4346 |
| P024 | `_eight_import_focused` | `filedialog.askopenfilename` | 4623 |
| P025 | `_eight_import_script` | `filedialog.askopenfilename` | 4793 |
| P026 | `decode_protocol` | `filedialog.askopenfilenames` | 5028 |
| P027 | `export_protocol_report` | `filedialog.asksaveasfilename` | 5040 |
| P028 | `analyze_pcaps` | `filedialog.askopenfilenames` | 5045 |
| P029 | `export_pcap_analysis` | `filedialog.asksaveasfilename` | 5060 |
| P030 | `run_memory_audit_snapshots` | `filedialog.askopenfilenames` | 5069 |
| P031 | `export_memory_audit` | `filedialog.asksaveasfilename` | 5086 |
| P032 | `assess_readback` | `filedialog.askopenfilenames` | 5091 |
| P033 | `export_readback` | `filedialog.asksaveasfilename` | 5102 |
| P034 | `export_assignment_comparison` | `filedialog.asksaveasfilename` | 5183 |
| P035 | `export_bank_comparison` | `filedialog.asksaveasfilename` | 5292 |
| P036 | `export_shared_memory` | `filedialog.asksaveasfilename` | 5330 |
| P037 | `export_live_readback` | `filedialog.asksaveasfilename` | 5336 |
| P038 | `capture_key2_snapshot` | `filedialog.asksaveasfilename` | 5375 |
| P039 | `compare_key2_snapshots` | `filedialog.askopenfilename` | 5394 |
| P040 | `compare_key2_snapshots` | `filedialog.askopenfilename` | 5397 |
| P041 | `select_baseline` | `filedialog.askopenfilename` | 5431 |

## Message call sites (150)

| ID | Source method | API | Line |
|---|---|---|---:|
| M001 | `save` | `messagebox.showerror` | 1614 |
| M002 | `_dropdown_create` | `messagebox.showwarning` | 1688 |
| M003 | `_dropdown_create` | `messagebox.showwarning` | 1690 |
| M004 | `_dropdown_delete` | `messagebox.askyesno` | 1699 |
| M005 | `_dropdown_export` | `messagebox.showerror` | 1711 |
| M006 | `apply_import` | `messagebox.askyesno` | 1741 |
| M007 | `_dropdown_import` | `messagebox.showerror` | 1752 |
| M008 | `_definitions_restore` | `messagebox.askyesno` | 1838 |
| M009 | `_definitions_export_json` | `messagebox.showerror` | 1850 |
| M010 | `_definitions_import_json` | `messagebox.askyesno` | 1876 |
| M011 | `_definitions_import_json` | `messagebox.showerror` | 1882 |
| M012 | `_insert_custom_wait` | `messagebox.showerror` | 2181 |
| M013 | `_macro_pull_from_form` | `messagebox.askyesno` | 2662 |
| M014 | `_macro_generate` | `messagebox.askyesno` | 2686 |
| M015 | `_macro_generate` | `messagebox.showerror` | 2700 |
| M016 | `_macro_apply_to_form` | `messagebox.showerror` | 2876 |
| M017 | `_macro_apply_to_form` | `messagebox.askyesno` | 2878 |
| M018 | `_macro_validate` | `messagebox.showerror` | 2894 |
| M019 | `_macro_copy_key` | `messagebox.showerror` | 2913 |
| M020 | `_macro_copy` | `messagebox.showerror` | 2923 |
| M021 | `_macro_open` | `messagebox.askyesno` | 2932 |
| M022 | `_macro_open` | `messagebox.showerror` | 2940 |
| M023 | `_macro_save` | `messagebox.showerror` | 2950 |
| M024 | `_macro_save_readable` | `messagebox.showerror` | 2958 |
| M025 | `_macro_clear` | `messagebox.askyesno` | 2961 |
| M026 | `_validate_key2_endpoint_move` | `messagebox.showwarning` | 3126 |
| M027 | `_workspace_confirm_leave` | `messagebox.askyesnocancel` | 3168 |
| M028 | `_workspace_save` | `messagebox.showerror` | 3263 |
| M029 | `_workspace_open` | `messagebox.showwarning` | 3273 |
| M030 | `_workspace_open` | `messagebox.showerror` | 3276 |
| M031 | `_workspace_open` | `messagebox.showerror` | 3284 |
| M032 | `_workspace_export_script` | `messagebox.showerror` | 3293 |
| M033 | `_workspace_import_script` | `messagebox.askyesno` | 3304 |
| M034 | `_workspace_import_script` | `messagebox.showerror` | 3333 |
| M035 | `_import_legacy_to_form` | `messagebox.askyesno` | 3356 |
| M036 | `_export_form_format` | `messagebox.showinfo` | 3365 |
| M037 | `_export_form_format` | `messagebox.showinfo` | 3374 |
| M038 | `_export_form_format` | `messagebox.showerror` | 3375 |
| M039 | `_import_form_format` | `messagebox.showinfo` | 3379 |
| M040 | `_import_form_format` | `messagebox.showinfo` | 3387 |
| M041 | `_import_form_format` | `messagebox.askyesno` | 3391 |
| M042 | `_import_form_format` | `messagebox.showinfo` | 3394 |
| M043 | `_import_form_format` | `messagebox.askyesno` | 3416 |
| M044 | `_import_form_format` | `messagebox.showinfo` | 3420 |
| M045 | `_import_form_format` | `messagebox.showerror` | 3421 |
| M046 | `_save_form_layout` | `messagebox.showerror` | 3430 |
| M047 | `_load_form_layout` | `messagebox.showerror` | 3448 |
| M048 | `_save_field_list` | `messagebox.showerror` | 3462 |
| M049 | `_load_field_list` | `messagebox.askyesno` | 3486 |
| M050 | `_load_field_list` | `messagebox.showerror` | 3488 |
| M051 | `load_session` | `messagebox.showwarning` | 3598 |
| M052 | `clear` | `messagebox.askyesno` | 3601 |
| M053 | `save_as` | `messagebox.showerror` | 3609 |
| M054 | `open_project` | `messagebox.showerror` | 3617 |
| M055 | `check_preview_date` | `messagebox.showwarning` | 3905 |
| M056 | `_designer_add_label` | `messagebox.showwarning` | 4055 |
| M057 | `_designer_add_label` | `messagebox.showwarning` | 4059 |
| M058 | `_designer_remove_label` | `messagebox.showinfo` | 4066 |
| M059 | `_manage_apply` | `messagebox.showwarning` | 4178 |
| M060 | `_designer_resize` | `messagebox.showwarning` | 4323 |
| M061 | `_designer_resize` | `messagebox.showwarning` | 4325 |
| M062 | `_designer_resize` | `messagebox.showwarning` | 4328 |
| M063 | `_designer_rename` | `messagebox.showinfo` | 4335 |
| M064 | `_designer_rename` | `messagebox.showwarning` | 4339 |
| M065 | `_designer_remove` | `messagebox.showinfo` | 4387 |
| M066 | `_designer_remove` | `messagebox.showwarning` | 4388 |
| M067 | `_designer_remove` | `messagebox.askyesno` | 4389 |
| M068 | `_designer_reset` | `messagebox.askyesno` | 4405 |
| M069 | `_refresh` | `messagebox.showerror` | 4475 |
| M070 | `_eight_import_focused` | `messagebox.askyesno` | 4629 |
| M071 | `_eight_import_focused` | `messagebox.showerror` | 4632 |
| M072 | `_poll_eight_transfer` | `messagebox.showerror` | 4658 |
| M073 | `_poll_eight_transfer` | `messagebox.showwarning` | 4663 |
| M074 | `_poll_eight_transfer` | `messagebox.showinfo` | 4667 |
| M075 | `_poll_eight_transfer` | `messagebox.showinfo` | 4670 |
| M076 | `_eight_load_focused` | `messagebox.askyesno` | 4681 |
| M077 | `_eight_save_focused` | `messagebox.showerror` | 4704 |
| M078 | `_eight_save_focused` | `messagebox.askyesno` | 4710 |
| M079 | `_eight_import_script` | `messagebox.showinfo` | 4806 |
| M080 | `_eight_import_script` | `messagebox.showerror` | 4807 |
| M081 | `_eight_load_notice` | `messagebox.showinfo` | 4810 |
| M082 | `_eight_save_notice` | `messagebox.showwarning` | 4815 |
| M083 | `_eight_save_notice` | `messagebox.showinfo` | 4828 |
| M084 | `_eight_save_notice` | `messagebox.showerror` | 4829 |
| M085 | `_apply_inline_eight_keys` | `messagebox.askyesno` | 4868 |
| M086 | `_apply_inline_eight_keys` | `messagebox.showinfo` | 4875 |
| M087 | `_apply_inline_eight_keys` | `messagebox.showerror` | 4878 |
| M088 | `_read_inline_eight_keys` | `messagebox.askyesno` | 4881 |
| M089 | `_read_inline_eight_keys` | `messagebox.showerror` | 4892 |
| M090 | `_compare_inline_eight_keys` | `messagebox.showwarning` | 4896 |
| M091 | `detect_device_configuration` | `messagebox.showinfo` | 4977 |
| M092 | `detect_device_configuration` | `messagebox.showinfo` | 5004 |
| M093 | `detect_device_configuration` | `messagebox.showwarning` | 5009 |
| M094 | `backup` | `messagebox.showinfo` | 5024 |
| M095 | `backup` | `messagebox.showerror` | 5025 |
| M096 | `decode_protocol` | `messagebox.showerror` | 5036 |
| M097 | `analyze_pcaps` | `messagebox.showwarning` | 5048 |
| M098 | `analyze_pcaps` | `messagebox.showerror` | 5056 |
| M099 | `export_pcap_analysis` | `messagebox.showerror` | 5063 |
| M100 | `_run_memory_audit` | `messagebox.showerror` | 5080 |
| M101 | `assess_readback` | `messagebox.showerror` | 5097 |
| M102 | `live_readback` | `messagebox.askyesno` | 5106 |
| M103 | `capture_assignment_comparison` | `messagebox.showwarning` | 5154 |
| M104 | `capture_assignment_comparison` | `messagebox.askyesno` | 5155 |
| M105 | `capture_assignment_comparison` | `messagebox.showerror` | 5174 |
| M106 | `export_assignment_comparison` | `messagebox.showinfo` | 5182 |
| M107 | `export_assignment_comparison` | `messagebox.showinfo` | 5186 |
| M108 | `live_key_mapping` | `messagebox.askyesno` | 5189 |
| M109 | `clear_bank_snapshots` | `messagebox.askyesno` | 5232 |
| M110 | `capture_bank_snapshot` | `messagebox.askyesno` | 5239 |
| M111 | `capture_bank_snapshot` | `messagebox.showerror` | 5255 |
| M112 | `export_bank_comparison` | `messagebox.showinfo` | 5291 |
| M113 | `run_shared_memory` | `messagebox.askyesno` | 5296 |
| M114 | `capture_key2_snapshot` | `messagebox.askyesno` | 5340 |
| M115 | `capture_key2_snapshot` | `messagebox.showinfo` | 5387 |
| M116 | `capture_key2_snapshot` | `messagebox.showerror` | 5391 |
| M117 | `compare_key2_snapshots` | `messagebox.showerror` | 5428 |
| M118 | `select_baseline` | `messagebox.showinfo` | 5443 |
| M119 | `select_baseline` | `messagebox.showerror` | 5448 |
| M120 | `write_device` | `messagebox.showerror` | 5452 |
| M121 | `write_device` | `messagebox.showerror` | 5466 |
| M122 | `write_device` | `messagebox.askyesno` | 5468 |
| M123 | `write_device` | `messagebox.askyesno` | 5478 |
| M124 | `write_device` | `messagebox.showinfo` | 5491 |
| M125 | `write_device` | `messagebox.showwarning` | 5498 |
| M126 | `write_device` | `messagebox.showwarning` | 5500 |
| M127 | `write_device` | `messagebox.showerror` | 5504 |
| M128 | `_a22_device_load` | `messagebox.showwarning` | 5520 |
| M129 | `_a22_device_load` | `messagebox.showwarning` | 5539 |
| M130 | `_a22_device_load` | `messagebox.showinfo` | 5556 |
| M131 | `_a22_device_load` | `messagebox.showerror` | 5557 |
| M132 | `_a22_device_save` | `messagebox.showwarning` | 5561 |
| M133 | `_a22_device_save` | `messagebox.askyesno` | 5576 |
| M134 | `_a22_device_save` | `messagebox.showinfo` | 5589 |
| M135 | `_a22_device_save` | `messagebox.showerror` | 5590 |
| M136 | `_a22_assign` | `messagebox.askyesno` | 5594 |
| M137 | `_a22_assign` | `messagebox.showinfo` | 5602 |
| M138 | `_a22_assign` | `messagebox.showerror` | 5603 |
| M139 | `_update_key_focus` | `messagebox.showinfo` | 5674 |
| M140 | `_update_key_focus` | `messagebox.showinfo` | 5678 |
| M141 | `_apply_viewer_timing` | `messagebox.showerror` | 5747 |
| M142 | `_insert_freeform_wait` | `messagebox.showerror` | 5806 |
| M143 | `apply_recording` | `messagebox.showerror` | 5945 |
| M144 | `_freeform_decode` | `messagebox.askyesno` | 5976 |
| M145 | `_freeform_decode` | `messagebox.showerror` | 5980 |
| M146 | `_freeform_paste_sayo` | `messagebox.showwarning` | 6021 |
| M147 | `_freeform_paste_sayo` | `messagebox.showerror` | 6028 |
| M148 | `_freeform_copy_sayo` | `messagebox.showerror` | 6041 |
| M149 | `_freeform_generate` | `messagebox.showwarning` | 6066 |
| M150 | `_freeform_generate` | `messagebox.showerror` | 6080 |
