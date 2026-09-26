// ===============================================
//  إعدادات المتجر + قائمة المنتجات
//  عدّل هذا الملف فقط لتحديث المنتجات والأسعار
// ===============================================

const STORE = {
  name: "Sky Avero",
  subtitle: "Coffee | قهوة مختصة",
  tagline: "قهوة مختصة V60 ☕ — علامة إماراتية مرخصة 🇦🇪",
  note: "كل بوكس يحتوي على 8 أكياس — اختر نكهاتك بنفسك",
  instagram: "skyavero",
  // رقم الواتساب بالصيغة الدولية بدون + ، مثال: 9715XXXXXXXX
  // إذا كان فاضي، يكون الطلب عن طريق رسائل الانستقرام
  whatsapp: "",
  currency: "درهم",
};

// لكل منتج: name, origin, category, price, oldPrice (اختياري), image (اختياري),
// description, badge (اختياري), available: false إذا نفد
const PRODUCTS = [
  { name: "Blueberry", origin: "Ethiopia", category: "إثيوبيا", price: 55, description: "قهوة إثيوبية مختصة بنكهة التوت الأزرق — بوكس 8 أكياس." },
  { name: "Roco", origin: "Ethiopia", category: "إثيوبيا", price: 55, description: "قهوة إثيوبية مختصة — بوكس 8 أكياس." },
  { name: "Hambela", origin: "Ethiopia", category: "إثيوبيا", price: 60, description: "قهوة إثيوبية من منطقة هامبيلا — بوكس 8 أكياس." },
  { name: "Santa Ana", origin: "Colombia", category: "كولومبيا", price: 55, description: "قهوة كولومبية مختصة — بوكس 8 أكياس." },
  { name: "Passion Fruit", origin: "Colombia", category: "كولومبيا", price: 70, description: "قهوة كولومبية بنكهة فاكهة الباشن فروت — بوكس 8 أكياس." },
  { name: "Berries", origin: "Colombia", category: "كولومبيا", price: 70, description: "قهوة كولومبية بنكهة التوتيات — بوكس 8 أكياس." },
  { name: "Strawberry", origin: "Colombia", category: "كولومبيا", price: 70, description: "قهوة كولومبية بنكهة الفراولة — بوكس 8 أكياس." },
  { name: "Grape", origin: "Colombia", category: "كولومبيا", price: 70, description: "قهوة كولومبية بنكهة العنب — بوكس 8 أكياس." },
  { name: "Mixed Coffee Box", origin: "Mix", category: "بوكس مشكّل", price: 65, description: "بوكس مشكّل من نكهاتنا — 8 أكياس.", badge: "اختر نكهاتك" },
];
