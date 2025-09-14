$fn=300;
//Wydruk w pionie i bez podpor
dlug=22;
srednica=12;
dlug_sruba=10;
dlug_wpust=6;
d_wpust=5;
sciecie_wpust=3;
d_gwint=2.5;
difference() {
    cylinder(dlug,d=srednica,center = true);
    translate([0,0,dlug/2-dlug_sruba/2+0.001]) {
        cylinder(dlug_sruba,d=4,center = true);
    }
    translate([0,0,-dlug/2+dlug_wpust/2-0.001]){
        intersection() {
          cylinder(dlug_wpust,d=d_wpust,center=true);
          cube([sciecie_wpust,d_wpust+0.001,dlug_wpust+0.001],center=true);
        }
    }
    translate([srednica/4,0,dlug/2-dlug_sruba/2])
      rotate([0,90,0])
        cylinder(srednica/2+0.001,d=d_gwint, center = true);
    translate([-srednica/4,0,dlug/2-dlug_sruba/2])
      rotate([0,90,0])
        cylinder(srednica/2+0.001,d=d_gwint, center = true);
    translate([srednica/4,0,-dlug/2+dlug_wpust/2])
      rotate([0,90,0])
        cylinder(srednica/2+0.001,d=d_gwint, center = true);
    translate([-srednica/4,0,-dlug/2+dlug_wpust/2])
      rotate([0,90,0])
        cylinder(srednica/2+0.001,d=d_gwint, center = true);
}